
if (allTraceData === undefined) {
    var allTraceData = {};
}
(function() { // IIFE to avoid variable collision
    let codelensID = "rs-chp12_dict3";  //fallback
    let partnerCodelens = document.currentScript.parentElement.querySelector(".pytutorVisualizer");
    if (partnerCodelens) {
        codelensID = partnerCodelens.id;
    }
    allTraceData[codelensID] = {"code": "eng2sp = {'three': 'tres', 'one': 'uno', 'two': 'dos'}\n\nvalue = eng2sp['two']\nprint(value)\n", "trace": [{"line": 1, "event": "step_line", "func_name": "<module>", "globals": {}, "ordered_globals": [], "stack_to_render": [], "heap": {}, "stdout": ""}, {"line": 3, "event": "step_line", "func_name": "<module>", "globals": {"eng2sp": ["REF", 1]}, "ordered_globals": ["eng2sp"], "stack_to_render": [], "heap": {"1": ["DICT", ["three", "tres"], ["one", "uno"], ["two", "dos"]]}, "stdout": ""}, {"line": 4, "event": "step_line", "func_name": "<module>", "globals": {"eng2sp": ["REF", 1], "value": "dos"}, "ordered_globals": ["eng2sp", "value"], "stack_to_render": [], "heap": {"1": ["DICT", ["three", "tres"], ["one", "uno"], ["two", "dos"]]}, "stdout": ""}, {"line": 4, "event": "return", "func_name": "<module>", "globals": {"eng2sp": ["REF", 1], "value": "dos"}, "ordered_globals": ["eng2sp", "value"], "stack_to_render": [], "heap": {"1": ["DICT", ["three", "tres"], ["one", "uno"], ["two", "dos"]]}, "stdout": "dos\n"}], "startingInstruction": 0};
})();