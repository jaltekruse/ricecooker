/*
 * Makes the WeBWorK exercises in a page of a PreTeXt book work offline in Kolibri, with WeBWorK's problem renderer
 * (PG) running in the browser, compiled to WebAssembly (https://github.com/jaltekruse/webwork-wasm), instead of on a
 * WeBWorK server.
 *
 * PreTeXt's own script for WeBWorK exercises, pretext-webwork.js, is used as it is: when a learner activates an
 * exercise, or checks their answers, it posts the problem and the answers to the server's render_rpc with jQuery, and
 * shows the problem the server sends back in an iframe, loading jQuery, MathJax and Bootstrap from the server's
 * webwork2_files. chef_pretext.py puts the PG engine and copies of those files in the book's dependency zip, at
 * <dependency zip>/webwork/, with the problems the book uses, and points each exercise's data-domain there. This
 * script answers the posts to render_rpc there with the engine, in the shape the server would.
 *
 * It also keeps each exercise's seed and the learner's last answers in localStorage, which Kolibri keeps for each
 * learner on its server and syncs between devices, shows them again when the learner comes back to the page, and
 * tells pretext_kolibri_scorm.js the score of each answer that is checked, which it reports to Kolibri.
 */
(function () {
  "use strict";

  var RENDER_RPC = "/webwork2/render_rpc";
  // where each exercise's seed and answers are kept, by the exercise's id
  var ANSWERS_KEY = "kolibri-pretext:webwork:";
  // the event pretext_kolibri_scorm.js listens to for scores
  var SCORE_EVENT = "kolibri-pretext:score";

  var thisScript = document.currentScript;
  // the engine is next to this script, at <dependency zip>/webwork/
  var engineURL = new URL(".", thisScript.src).href;
  var pg = null;

  function engine() {
    if (!pg) {
      pg = new window.PGClient({ baseURL: engineURL });
    }
    return pg;
  }

  function storage() {
    try {
      return window.localStorage;
    } catch (e) {
      return null;
    }
  }

  function loadAnswers(id) {
    var store = storage();
    try {
      return JSON.parse((store && store.getItem(ANSWERS_KEY + id)) || "null");
    } catch (e) {
      return null;
    }
  }

  function saveAnswers(id, saved) {
    var store = storage();
    if (!store) {
      return;
    }
    try {
      store.setItem(ANSWERS_KEY + id, JSON.stringify(saved));
    } catch (e) {
      // too big to keep
    }
  }

  function containers() {
    return Array.prototype.slice.call(document.querySelectorAll("[data-kolibri-webwork]"));
  }

  // The form fields pretext-webwork.js posts, url-encoded, with checkboxes' values joined the way PG takes them
  function parseForm(body) {
    var fields = {};
    new URLSearchParams(String(body || "")).forEach(function (value, name) {
      fields[name] = name in fields ? fields[name] + "\0" + value : value;
    });
    return fields;
  }

  // The fields that are answers, rather than the request's own settings
  var REQUEST_FIELDS = [
    "problemSeed", "problemUUID", "psvn", "courseName", "courseID", "user", "userID", "passwd", "displayMode",
    "session_key", "outputformat", "language", "showSummary", "disableCookies", "showSolutions", "showHints",
    "forcePortNumber", "sourceFilePath", "problemSource", "rawProblemSource", "answersSubmitted", "WWsubmit",
    "WWcorrectAnsOnly",
  ];

  function answersIn(fields) {
    var answers = {};
    Object.keys(fields).forEach(function (name) {
      if (REQUEST_FIELDS.indexOf(name) === -1) {
        answers[name] = fields[name];
      }
    });
    return answers;
  }

  var escapeHTML = function (text) {
    return String(text == null ? "" : text).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  };

  // A TikZ or LaTeX picture, which the engine leaves for TikZJax to compile in the page, as in PGClient.problemPage
  function tikzElement(spec, imgTag) {
    var attr = function (name) {
      return (imgTag.match(new RegExp("\\b" + name + '="([^"]*)"')) || [])[1];
    };
    var packages = {};
    (spec.texPackages || []).forEach(function (pkg) {
      if (pkg[0] !== "tikz" && pkg[0] !== "xcolor") {
        packages[pkg[0]] = pkg[1] || "";
      }
    });
    var env = spec.environment || ["", ""];
    var tex = env[0] ? "\\begin{" + env[0] + "}" + (env[1] ? "[" + env[1] + "]" : "") + "\n" + spec.tex + "\n\\end{" +
      env[0] + "}" : spec.tex;
    var width = attr("width");
    var height = attr("height");
    return '<span class="pg-tikz" style="display:inline-block;vertical-align:middle">' +
      '<script type="text/tikz" data-tex-packages="' + escapeHTML(JSON.stringify(packages)) + '"' +
      ' data-tikz-libraries="' + escapeHTML(spec.tikzLibraries || "") + '"' +
      ' data-add-to-preamble="' + escapeHTML(spec.addToPreamble || "") + '"' +
      ' data-aria-label="' + escapeHTML(attr("alt") || "") + '"' +
      ' data-width="' + escapeHTML(width || "100") + '" data-height="' + escapeHTML(height || width || "100") + '">' +
      tex.replace(/<\/script/gi, "<\\/script") + "</script></span>";
  }

  // The problem's text, with the files PG made (images, graphs) linked where they are
  function problemText(result) {
    var text = result.body_text || "";
    var usesTikz = false;
    Object.keys(result.files || {}).forEach(function (name) {
      var file = result.files[name];
      if (file && typeof file === "object") {
        if (!file.latex) {
          return;
        }
        var img = new RegExp('<img\\b[^>]*\\bsrc="pg_temp/' + name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") +
          '"[^>]*>', "g");
        text = text.replace(img, function (tag) {
          usesTikz = true;
          return tikzElement(file.latex, tag);
        });
        return;
      }
      text = text.split("pg_temp/" + name).join(new URL(file, engineURL).href);
    });
    return { text: text, usesTikz: usesTikz };
  }

  function assetFiles(files) {
    return (files || []).map(function (file) {
      return { file: engine().assetURL(file.file), external: "1", attributes: file.attributes || {} };
    });
  }

  // Shows the correct answers when the learner reveals them, as WeBWorK's server does
  function revealScript(id, answers) {
    var correct = {};
    Object.keys(answers || {}).forEach(function (name) {
      correct[name] = {
        correct_ans: answers[name].correct_ans,
        correct_ans_latex_string: answers[name].correct_ans_latex_string,
      };
    });
    return "<script>window.addEventListener('load', function () { setTimeout(function () { " +
      "parent.WWshowCorrect(" + JSON.stringify(id) + ", " + JSON.stringify(correct).replace(/</g, "\\u003c") +
      "); }, 0); });</script>";
  }

  // What WeBWorK's server would send back to pretext-webwork.js for a post to render_rpc
  function renderRPC(fields) {
    var id = fields.problemUUID;
    var submitted = fields.answersSubmitted === "1";
    var reveal = submitted && fields.WWcorrectAnsOnly === "1";
    var seed = parseInt(fields.problemSeed, 10) || 1;
    var answers = submitted ? answersIn(fields) : {};
    var restoring = false;
    if (!submitted) {
      // Activating the exercise: show the learner's last answers to it, if they were for this seed
      var saved = loadAnswers(id);
      if (saved && saved.seed === seed && saved.answers && Object.keys(saved.answers).length) {
        answers = saved.answers;
        restoring = true;
      }
    }
    var request = {
      sourceFilePath: fields.sourceFilePath,
      problemSeed: seed,
      problemUUID: id,
      inputs: answers,
      processAnswers: submitted || restoring ? 1 : 0,
      showHints: fields.showHints === "1" ? 1 : 0,
      showSolutions: fields.showSolutions === "1" ? 1 : 0,
      showFeedback: submitted || restoring ? 1 : 0,
      showAttemptResults: submitted || restoring ? 1 : 0,
      showCorrectAnswers: reveal ? 2 : 0,
      answersAvailable: reveal ? 1 : 0,
      language: fields.language || "en",
    };
    return engine().render(request).then(function (result) {
      if (submitted && !reveal) {
        saveAnswers(id, { seed: seed, answers: answers });
        document.dispatchEvent(new CustomEvent(SCORE_EVENT, {
          detail: { id: id, score: result.score || 0, answer: JSON.stringify(answers) },
        }));
      } else if (!submitted && !restoring) {
        saveAnswers(id, { seed: seed, answers: {} });
      }
      var problem = problemText(result);
      var text = problem.text;
      if (result.errors) {
        text += '<div class="alert alert-danger"><pre>' + escapeHTML(result.errors) + "</pre></div>";
      }
      if (reveal) {
        text += revealScript(id, result.answers);
      }
      var extraCSS = assetFiles(result.extra_css_files);
      var extraJS = assetFiles(result.extra_js_files);
      if (problem.usesTikz) {
        extraCSS.push({ file: engineURL + "vendor/tikzjax/fonts.css", external: "1" });
        extraJS.push({ file: engineURL + "vendor/tikzjax/tikzjax.js", external: "1" });
      }
      return {
        rh_result: {
          text: text,
          flags: result.flags || {},
          problem_result: submitted || restoring ? { score: result.score || 0 } : {},
          answers: result.answers,
          session_key: "",
          errors: result.errors,
        },
        inputs_ref: { problemSeed: seed, problemUUID: id, psvn: "" },
        lang: fields.language || "en",
        dir: "ltr",
        formLanguage: fields.language || "en",
        showSummary: 1,
        forcePortNumber: "",
        extra_css_files: extraCSS,
        extra_js_files: extraJS,
      };
    });
  }

  // Answer pretext-webwork.js's posts to render_rpc at the engine, which it makes with $.post(url, data, success, type)
  function hookJQueryPost() {
    var $ = window.jQuery;
    if (!$ || $.post.kolibriWebwork) {
      return;
    }
    var post = $.post;
    $.post = function (url, data, success) {
      var target = String(url);
      if (target.indexOf(engineURL) === 0 && target.slice(-RENDER_RPC.length) === RENDER_RPC) {
        var fields = parseForm(data);
        var done = $.Deferred();
        renderRPC(fields).then(
          function (response) {
            if (typeof success === "function") {
              success(response);
            }
            done.resolve(response);
          },
          function (error) {
            console.error("WeBWorK problem " + fields.sourceFilePath + " could not be shown", error);
            var container = document.getElementById(fields.problemUUID);
            var loader = container && container.querySelector(":scope > div[tabindex='-1']");
            if (loader) {
              loader.textContent = "This problem could not be shown.";
            }
            done.reject(error);
          },
        );
        return done.promise();
      }
      return post.apply(this, arguments);
    };
    $.post.kolibriWebwork = true;
  }

  // pretext-webwork.js loads PreTeXt's knowl.js and theme.css in the problem's iframe from _static/ next to the page,
  // which, in Kolibri, is in the dependency zip
  function hookProblemFrames() {
    var srcdoc = Object.getOwnPropertyDescriptor(HTMLIFrameElement.prototype, "srcdoc");
    var pretextScript = document.querySelector('script[src*="pretext-webwork.js"]');
    if (!srcdoc || !pretextScript) {
      return;
    }
    // .../_static/pretext/js/dist/pretext-webwork.js
    var staticURL = new URL("../../../", pretextScript.src).href;
    Object.defineProperty(HTMLIFrameElement.prototype, "srcdoc", {
      configurable: true,
      enumerable: srcdoc.enumerable,
      get: function () {
        return srcdoc.get.call(this);
      },
      set: function (html) {
        if (this.classList && this.classList.contains("problem-iframe") && typeof html === "string") {
          html = html.replace(/(src|href)="_static\//g, '$1="' + staticURL);
        }
        srcdoc.set.call(this, html);
      },
    });
  }

  function start() {
    hookJQueryPost();
    containers().forEach(function (container) {
      // pretext-webwork.js makes the render_rpc URL from data-domain, which needs to be absolute
      container.dataset.domain = new URL(container.dataset.domain, document.baseURI).href.replace(/\/+$/, "");
      // Show the exercises the learner has worked on as they left them
      var saved = loadAnswers(container.id);
      if (saved && typeof saved.seed === "number") {
        container.dataset.seed = String(saved.seed);
        if (saved.answers && Object.keys(saved.answers).length && typeof window.handleWW === "function") {
          window.handleWW(container.id);
        }
      }
    });
  }

  hookProblemFrames();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
