
if (allTraceData === undefined) {
    var allTraceData = {};
}
(function() { // IIFE to avoid variable collision
    let codelensID = "rs-appcon1";  //fallback
    let partnerCodelens = document.currentScript.parentElement.querySelector(".pytutorVisualizer");
    if (partnerCodelens) {
        codelensID = partnerCodelens.id;
    }
    allTraceData[codelensID] = {"code": "origlist = [45, 32, 88]\n\noriglist.append(\"cat\")\n", "trace": [{"line": 1, "event": "step_line", "func_name": "<module>", "globals": {}, "ordered_globals": [], "stack_to_render": [], "heap": {}, "stdout": ""}, {"line": 3, "event": "step_line", "func_name": "<module>", "globals": {"origlist": ["REF", 1]}, "ordered_globals": ["origlist"], "stack_to_render": [], "heap": {"1": ["LIST", 45, 32, 88]}, "stdout": ""}, {"line": 3, "event": "return", "func_name": "<module>", "globals": {"origlist": ["REF", 1]}, "ordered_globals": ["origlist"], "stack_to_render": [], "heap": {"1": ["LIST", 45, 32, 88, "cat"]}, "stdout": ""}], "startingInstruction": 0};
})();