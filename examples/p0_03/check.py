def check(mart, params):
    return [{"LABEL": params["label"], "SOURCE": "AFTER", "ARGUMENT": "",
             "CNT": 0, "TOTAL": mart.total_apps(), "METRIC": 0.0,
             "APP_IDS": [], "RESULT": "PASS", "CONFIDENCE": "HIGH"}]
