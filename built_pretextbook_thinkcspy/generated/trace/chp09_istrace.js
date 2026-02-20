
if (allTraceData === undefined) {
    var allTraceData = {};
}
(function() { // IIFE to avoid variable collision
    let codelensID = "rs-chp09_istrace";  //fallback
    let partnerCodelens = document.currentScript.parentElement.querySelector(".pytutorVisualizer");
    if (partnerCodelens) {
        codelensID = partnerCodelens.id;
    }
    allTraceData[codelensID] = {"code": "a = [81, 82, 83]\nb = [81, 82, 83]\n\nprint(a is b)\nprint(a == b)\n", "trace": [{"line": 1, "event": "step_line", "func_name": "<module>", "globals": {}, "ordered_globals": [], "stack_to_render": [], "heap": {}, "stdout": ""}, {"line": 2, "event": "step_line", "func_name": "<module>", "globals": {"a": ["REF", 1]}, "ordered_globals": ["a"], "stack_to_render": [], "heap": {"1": ["LIST", 81, 82, 83]}, "stdout": ""}, {"line": 4, "event": "step_line", "func_name": "<module>", "globals": {"a": ["REF", 1], "b": ["REF", 2]}, "ordered_globals": ["a", "b"], "stack_to_render": [], "heap": {"1": ["LIST", 81, 82, 83], "2": ["LIST", 81, 82, 83]}, "stdout": ""}, {"line": 5, "event": "step_line", "func_name": "<module>", "globals": {"a": ["REF", 1], "b": ["REF", 2]}, "ordered_globals": ["a", "b"], "stack_to_render": [], "heap": {"1": ["LIST", 81, 82, 83], "2": ["LIST", 81, 82, 83]}, "stdout": "False\n"}, {"line": 5, "event": "return", "func_name": "<module>", "globals": {"a": ["REF", 1], "b": ["REF", 2]}, "ordered_globals": ["a", "b"], "stack_to_render": [], "heap": {"1": ["LIST", 81, 82, 83], "2": ["LIST", 81, 82, 83]}, "stdout": "False\nTrue\n"}], "startingInstruction": 0};
})();