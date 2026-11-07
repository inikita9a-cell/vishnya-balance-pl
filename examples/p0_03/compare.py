from engine.steps import compare as builtin
def compare(union_df, cfg, params, issues):
    result = builtin(union_df, issues=issues)
    mask = result.PATH.eq(params["ignore_path"])
    result.loc[mask, "CHANGE_TYPE"] = "SAME"
    result.loc[mask, "DIFF_FLAG"] = 0
    return result
