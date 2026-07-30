
if (allTraceData === undefined) {
    var allTraceData = {};
}
(function() { // IIFE to avoid variable collision
    let codelensID = "rs-chp12_dict1";  //fallback
    let partnerCodelens = document.currentScript.parentElement.querySelector(".pytutorVisualizer");
    if (partnerCodelens) {
        codelensID = partnerCodelens.id;
    }
    allTraceData[codelensID] = {"code": "eng2sp = {}\neng2sp['one'] = 'uno'\neng2sp['two'] = 'dos'\neng2sp['three'] = 'tres'\n", "trace": [{"line": 1, "event": "step_line", "func_name": "<module>", "globals": {}, "ordered_globals": [], "stack_to_render": [], "heap": {}, "stdout": ""}, {"line": 2, "event": "step_line", "func_name": "<module>", "globals": {"eng2sp": ["REF", 1]}, "ordered_globals": ["eng2sp"], "stack_to_render": [], "heap": {"1": ["DICT"]}, "stdout": ""}, {"line": 3, "event": "step_line", "func_name": "<module>", "globals": {"eng2sp": ["REF", 1]}, "ordered_globals": ["eng2sp"], "stack_to_render": [], "heap": {"1": ["DICT", ["one", "uno"]]}, "stdout": ""}, {"line": 4, "event": "step_line", "func_name": "<module>", "globals": {"eng2sp": ["REF", 1]}, "ordered_globals": ["eng2sp"], "stack_to_render": [], "heap": {"1": ["DICT", ["one", "uno"], ["two", "dos"]]}, "stdout": ""}, {"line": 4, "event": "return", "func_name": "<module>", "globals": {"eng2sp": ["REF", 1]}, "ordered_globals": ["eng2sp"], "stack_to_render": [], "heap": {"1": ["DICT", ["one", "uno"], ["two", "dos"], ["three", "tres"]]}, "stdout": ""}], "startingInstruction": 0};
})();