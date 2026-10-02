"""Reviewed v1 risk physical contract; no runtime regeneration of expected definitions."""

V1_RISK_TABLES = (
    "operator_trading_configuration",
    "trade_proposal",
    "approved_order_intent",
    "paper_submission_preview",
    "paper_execution_authorization",
)

V1_RISK_CONTRACT: dict[str, str] = {
    "column:operator_trading_configuration.risk_contract": "jsonb:false",
    "trigger:operator_trading_configuration.v1_entry_risk_guard": (
        "CREATE TRIGGER v1_entry_risk_guard BEFORE INSERT OR UPDATE ON public.operato"
        "r_trading_configuration FOR EACH ROW EXECUTE FUNCTION v1_entry_risk_guard():"
        "O"
    ),
    "column:trade_proposal.risk_contract": "jsonb:false",
    "trigger:trade_proposal.v1_entry_risk_guard": (
        "CREATE TRIGGER v1_entry_risk_guard BEFORE INSERT OR UPDATE ON public.trade_p"
        "roposal FOR EACH ROW EXECUTE FUNCTION v1_entry_risk_guard():O"
    ),
    "column:approved_order_intent.risk_contract": "jsonb:false",
    "trigger:approved_order_intent.v1_entry_risk_guard": (
        "CREATE TRIGGER v1_entry_risk_guard BEFORE INSERT OR UPDATE ON public.approve"
        "d_order_intent FOR EACH ROW EXECUTE FUNCTION v1_entry_risk_guard():O"
    ),
    "column:paper_submission_preview.risk_contract": "jsonb:false",
    "trigger:paper_submission_preview.v1_entry_risk_guard": (
        "CREATE TRIGGER v1_entry_risk_guard BEFORE INSERT OR UPDATE ON public.paper_s"
        "ubmission_preview FOR EACH ROW EXECUTE FUNCTION v1_entry_risk_guard():O"
    ),
    "column:paper_execution_authorization.risk_contract": "jsonb:false",
    "trigger:paper_execution_authorization.v1_entry_risk_guard": (
        "CREATE TRIGGER v1_entry_risk_guard BEFORE INSERT OR UPDATE ON public.paper_e"
        "xecution_authorization FOR EACH ROW EXECUTE FUNCTION v1_entry_risk_guard():O"
    ),
    "function:v1_entry_risk_guard": (
        "3bcaba4d"
        + "353394d8"
        + "07e058e2"
        + "cab2fbde"
        + "0c0dab20"
        + "f9a3a987"
        + "c387fcc7"
        + "7b3a084c"
    ),
}
