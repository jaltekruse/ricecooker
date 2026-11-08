/*
 * Reports a learner's answers to the exercises on a page of a PreTeXt book to Kolibri, which shows them as the
 * learner's progress on the page: the page's score, from 0 to 1, with a perfect score completing it.
 *
 * chef_pretext.py adds this script to every page it imports. It works with the books as their authors built them,
 * whether for the web or for Runestone, with no Runestone server: Runestone's components hand every answer to
 * RunestoneBase.prototype.logBookEvent, which logs it to the server when there is one, so that is wrapped to score
 * the answer too. DoenetML activities report their scores to the page with the SPLICE protocol, which Runestone's
 * SpliceWrapper also hands to logBookEvent.
 *
 * Kolibri gives HTML5 apps a SCORM 1.2 API, on the app's window in newer versions of Kolibri and on its parent in
 * older ones, and makes the learner's progress on the app the SCORM score, (raw - min) / (max - min). Kolibri also
 * keeps the app's SCORM data and localStorage for each learner, which is where scores and DoenetML activities' work
 * are kept between visits. Runestone's components keep their own answers in localStorage.
 *
 * PreTeXt's SCORM builds do much the same with js/ptx_scorm_events.js, made for LMSs that show a whole book as one
 * SCORM package, this is made for a Kolibri resource for each page.
 */
(function () {
  "use strict";

  // Components, by data-component, that grade the answers given to them. An activecode is only graded when it has
  // unit tests, the rest, like shortanswer, poll and selectquestion (which needs the Runestone server) aren't.
  var GRADED_COMPONENTS = [
    "multiplechoice",
    "fillintheblank",
    "parsons",
    "hparsons",
    "dragndrop",
    "clickablearea",
    "matching",
    "doenet",
    "splice",
  ];
  // logBookEvent events that are answers being graded
  var GRADED_EVENTS = [
    "mChoice",
    "fillb",
    "parsons",
    "hparsonsAnswer",
    "dragNdrop",
    "clickableArea",
    "matching",
    "unittest",
    "SPLICE.reportScoreAndState",
    "webwork",
  ];
  // SCORM 1.2 interaction types for each event, see cmi.interactions.n.type
  var INTERACTION_TYPES = {
    mChoice: "choice",
    clickableArea: "choice",
    fillb: "fill-in",
    webwork: "fill-in",
    parsons: "sequencing",
    hparsonsAnswer: "sequencing",
    dragNdrop: "matching",
    matching: "matching",
    unittest: "performance",
  };
  // where DoenetML activities' work is kept, in localStorage, which Kolibri keeps for each learner
  var SPLICE_STATE_KEY = "kolibri-pretext:splice-state:";
  // SCORM 1.2 limits cmi.suspend_data to 4096 characters
  var SUSPEND_DATA_LIMIT = 4096;

  var api = null;
  var gradedIds = [];
  var scores = {};

  function findApi() {
    var win = window;
    for (var depth = 0; win && depth < 10; depth++) {
      try {
        if (win.API && typeof win.API.LMSSetValue === "function") {
          return win.API;
        }
      } catch (e) {
        // a window from another origin
      }
      if (win.parent === win) {
        break;
      }
      win = win.parent;
    }
    return null;
  }

  function getValue(name) {
    try {
      return api ? api.LMSGetValue(name) : "";
    } catch (e) {
      return "";
    }
  }

  function setValue(name, value) {
    try {
      if (api) {
        api.LMSSetValue(name, String(value));
      }
    } catch (e) {
      // keep going without that value
    }
  }

  function storage() {
    try {
      return window.localStorage;
    } catch (e) {
      // e.g. a sandbox without allow-same-origin, like Studio's previews
      return null;
    }
  }

  // Unit tests come after a line of "====" in the code in the page, which Runestone moves to the activecode's suffix
  // when it makes the activecode
  function hasUnitTests(node) {
    var code = node.querySelector("textarea");
    var component = window.componentMap && window.componentMap[node.id];
    var tests = (code ? code.value : "") + ((component && component.suffix) || "");
    return tests.indexOf("unittest") !== -1;
  }

  function findGradedComponents() {
    var ids = [];
    var nodes = document.querySelectorAll("[data-component]");
    for (var i = 0; i < nodes.length; i++) {
      var node = nodes[i];
      var type = node.getAttribute("data-component");
      var graded = GRADED_COMPONENTS.indexOf(type) !== -1;
      if (type === "activecode") {
        graded = hasUnitTests(node);
      }
      if (graded && node.id && !node.closest("[data-optional]") && ids.indexOf(node.id) === -1) {
        ids.push(node.id);
      }
    }
    return ids;
  }

  // The graded component an event is about: the event's div_id is usually the component's id, but can be the id of
  // an element inside it, like an activecode's editor
  function gradedId(divId) {
    if (gradedIds.indexOf(divId) !== -1) {
      return divId;
    }
    var node = divId ? document.getElementById(divId) : null;
    for (; node; node = node.parentElement) {
      if (node.id && gradedIds.indexOf(node.id) !== -1) {
        return node.id;
      }
    }
    return null;
  }

  // The score from 0 to 1 an answer got
  function scoreOf(eventInfo) {
    if (eventInfo.event === "unittest") {
      // act is like "percent:66.67:passed:2:failed:1"
      var match = /percent:([\d.]+)/.exec(eventInfo.act || "");
      return match ? Math.min(parseFloat(match[1]) / 100, 1) : null;
    }
    var percent = eventInfo.percent;
    if (typeof percent === "string" && percent !== "") {
      percent = parseFloat(percent);
    }
    if (typeof percent === "number" && !isNaN(percent)) {
      return Math.max(0, Math.min(percent > 1 ? percent / 100 : percent, 1));
    }
    if (eventInfo.correct === true || eventInfo.correct === "T") {
      return 1;
    }
    if (eventInfo.correct === false || eventInfo.correct === "F") {
      return 0;
    }
    return null;
  }

  function loadScores() {
    try {
      var saved = JSON.parse(getValue("cmi.suspend_data") || "{}");
      return saved && typeof saved.scores === "object" ? saved.scores : {};
    } catch (e) {
      return {};
    }
  }

  // Tell Kolibri the page's score, the mean of its exercises' scores, with those not answered yet counting as 0
  function reportScore() {
    if (!api || !gradedIds.length) {
      // a page without exercises, which Kolibri completes by the time spent on it
      return;
    }
    var total = 0;
    var kept = {};
    for (var i = 0; i < gradedIds.length; i++) {
      var id = gradedIds[i];
      if (typeof scores[id] === "number") {
        total += scores[id];
        kept[id] = Math.round(scores[id] * 1000) / 1000;
      }
    }
    var suspendData = JSON.stringify({ scores: kept });
    if (suspendData.length <= SUSPEND_DATA_LIMIT) {
      setValue("cmi.suspend_data", suspendData);
    }
    var score = total / gradedIds.length;
    setValue("cmi.core.score.min", 0);
    setValue("cmi.core.score.max", 100);
    setValue("cmi.core.score.raw", Math.round(score * 10000) / 100);
    setValue("cmi.core.lesson_status", score >= 1 ? "passed" : "incomplete");
    try {
      api.LMSCommit("");
    } catch (e) {
      // Kolibri saves every value as it is set
    }
  }

  function recordInteraction(id, eventInfo, score) {
    var index = parseInt(getValue("cmi.interactions._count"), 10);
    if (isNaN(index)) {
      return;
    }
    var prefix = "cmi.interactions." + index + ".";
    setValue(prefix + "id", id.replace(/[^A-Za-z0-9_.:-]/g, "_").slice(0, 255));
    if (INTERACTION_TYPES[eventInfo.event]) {
      setValue(prefix + "type", INTERACTION_TYPES[eventInfo.event]);
    }
    var response = eventInfo.answer !== undefined ? eventInfo.answer : eventInfo.act;
    if (response !== undefined && response !== null) {
      setValue(prefix + "student_response", String(response).slice(0, 255));
    }
    setValue(prefix + "result", score >= 1 ? "correct" : score <= 0 ? "wrong" : String(score));
  }

  function saveSpliceState(id, eventInfo) {
    var store = storage();
    if (store && typeof eventInfo.answer === "string") {
      try {
        store.setItem(SPLICE_STATE_KEY + id, eventInfo.answer);
      } catch (e) {
        // too big to keep
      }
    }
  }

  function onBookEvent(component, eventInfo) {
    if (!eventInfo || GRADED_EVENTS.indexOf(eventInfo.event) === -1) {
      return;
    }
    var id = gradedId(eventInfo.div_id || (component && component.divid));
    if (eventInfo.event === "SPLICE.reportScoreAndState" && eventInfo.div_id) {
      saveSpliceState(eventInfo.div_id, eventInfo);
    }
    var score = scoreOf(eventInfo);
    if (!id || score === null) {
      return;
    }
    scores[id] = score;
    recordInteraction(id, eventInfo, score);
    reportScore();
  }

  function hookRunestone() {
    var base = window.RunestoneBase;
    if (!base || !base.prototype || base.prototype.logBookEvent.__kolibri) {
      return;
    }
    var logBookEvent = base.prototype.logBookEvent;
    var hooked = function (eventInfo) {
      // logBookEvent fills in eventInfo, like its percent, before it does anything asynchronous
      var result = logBookEvent.apply(this, arguments);
      try {
        onBookEvent(this, eventInfo);
      } catch (e) {
        console.error("Could not report an answer to Kolibri", e);
      }
      return result;
    };
    hooked.__kolibri = true;
    base.prototype.logBookEvent = hooked;
  }

  // Runestone's SpliceWrapper asks the Runestone server for a DoenetML activity's saved work, answer from what this
  // kept in localStorage instead
  function hookSplice() {
    var wrapper = window.spliceWrapper;
    if (!wrapper || wrapper.getSavedState.__kolibri) {
      return;
    }
    var getSavedState = function (location) {
      var store = storage();
      var saved = store ? store.getItem(SPLICE_STATE_KEY + location) : null;
      if (saved === null) {
        return Promise.resolve(null);
      }
      try {
        return Promise.resolve({ detail: { answer: JSON.parse(saved) } });
      } catch (e) {
        return Promise.resolve(null);
      }
    };
    getSavedState.__kolibri = true;
    wrapper.getSavedState = getSavedState;
  }

  function start() {
    hookRunestone();
    hookSplice();
    api = findApi();
    gradedIds = findGradedComponents();
    if (!api || !gradedIds.length) {
      return;
    }
    try {
      api.LMSInitialize("");
    } catch (e) {
      // already initialized
    }
    scores = loadScores();
    // report straight away, so Kolibri shows the page's score, and doesn't complete the page by time spent on it
    reportScore();
  }

  // Runestone's bundle sets window.RunestoneBase when it loads, which is before the components are made, after the
  // page has loaded
  hookRunestone();
  hookSplice();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
  document.addEventListener("runestone:pre-login-complete", function () {
    hookRunestone();
    hookSplice();
  });
})();
