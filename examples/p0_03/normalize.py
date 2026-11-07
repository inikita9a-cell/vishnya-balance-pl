from engine.steps import flatten_pair
def normalize(before, after, cfg, params, app_id, issues):
    before = {**before, "custom_marker": params["marker"]}
    after = {**after, "custom_marker": params["marker"]}
    return flatten_pair(before, after, cfg, app_id=app_id, issues=issues)
