from engine.aggregates import facts as builtin
def facts(comparison, segments, cfg, params):
    table, members = builtin(comparison, segments, cfg)
    table["CUSTOM_DIMENSION"] = params["dimension"]
    return table, members
