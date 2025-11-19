
if (allTraceData === undefined) {
    var allTraceData = {};
}
(function() { // IIFE to avoid variable collision
    let codelensID = "rs-ch02_9_cl";  //fallback
    let partnerCodelens = document.currentScript.parentElement.querySelector(".pytutorVisualizer");
    if (partnerCodelens) {
        codelensID = partnerCodelens.id;
    }
    allTraceData[codelensID] = {"code": "message = \"What's up, Doc?\"\nn = 17\npi = 3.14159\n\nprint(message)\nprint(n)\nprint(pi)\n", "trace": [{"line": 1, "event": "step_line", "func_name": "<module>", "globals": {}, "ordered_globals": [], "stack_to_render": [], "heap": {}, "stdout": ""}, {"line": 2, "event": "step_line", "func_name": "<module>", "globals": {"message": "What's up, Doc?"}, "ordered_globals": ["message"], "stack_to_render": [], "heap": {}, "stdout": ""}, {"line": 3, "event": "step_line", "func_name": "<module>", "globals": {"message": "What's up, Doc?", "n": 17}, "ordered_globals": ["message", "n"], "stack_to_render": [], "heap": {}, "stdout": ""}, {"line": 5, "event": "step_line", "func_name": "<module>", "globals": {"message": "What's up, Doc?", "n": 17, "pi": 3.1416}, "ordered_globals": ["message", "n", "pi"], "stack_to_render": [], "heap": {}, "stdout": ""}, {"line": 6, "event": "step_line", "func_name": "<module>", "globals": {"message": "What's up, Doc?", "n": 17, "pi": 3.1416}, "ordered_globals": ["message", "n", "pi"], "stack_to_render": [], "heap": {}, "stdout": "What's up, Doc?\n"}, {"line": 7, "event": "step_line", "func_name": "<module>", "globals": {"message": "What's up, Doc?", "n": 17, "pi": 3.1416}, "ordered_globals": ["message", "n", "pi"], "stack_to_render": [], "heap": {}, "stdout": "What's up, Doc?\n17\n"}, {"line": 7, "event": "return", "func_name": "<module>", "globals": {"message": "What's up, Doc?", "n": 17, "pi": 3.1416}, "ordered_globals": ["message", "n", "pi"], "stack_to_render": [], "heap": {}, "stdout": "What's up, Doc?\n17\n3.14159\n"}], "startingInstruction": 0};
})();