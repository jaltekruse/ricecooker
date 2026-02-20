
if (allTraceData === undefined) {
    var allTraceData = {};
}
(function() { // IIFE to avoid variable collision
    let codelensID = "rs-ch12_dict4a";  //fallback
    let partnerCodelens = document.currentScript.parentElement.querySelector(".pytutorVisualizer");
    if (partnerCodelens) {
        codelensID = partnerCodelens.id;
    }
    allTraceData[codelensID] = {"code": "inventory = {'apples': 430, 'bananas': 312, 'oranges': 525, 'pears': 217}\n\ninventory['pears'] = 0\n", "trace": [{"line": 1, "event": "step_line", "func_name": "<module>", "globals": {}, "ordered_globals": [], "stack_to_render": [], "heap": {}, "stdout": ""}, {"line": 3, "event": "step_line", "func_name": "<module>", "globals": {"inventory": ["REF", 1]}, "ordered_globals": ["inventory"], "stack_to_render": [], "heap": {"1": ["DICT", ["apples", 430], ["bananas", 312], ["oranges", 525], ["pears", 217]]}, "stdout": ""}, {"line": 3, "event": "return", "func_name": "<module>", "globals": {"inventory": ["REF", 1]}, "ordered_globals": ["inventory"], "stack_to_render": [], "heap": {"1": ["DICT", ["apples", 430], ["bananas", 312], ["oranges", 525], ["pears", 0]]}, "stdout": ""}], "startingInstruction": 0};
})();