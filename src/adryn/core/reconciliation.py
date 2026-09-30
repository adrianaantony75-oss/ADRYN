from __future__ import annotations

import pandas as pd


def reconcile_contracts(contracts: pd.DataFrame) -> pd.DataFrame:
    reconciled = contracts.copy()
    reconciled["value_delta"] = (
        reconciled["crm_contract_value"] - reconciled["erp_contract_value"]
    ).round(2)
    reconciled["status_mismatch"] = reconciled["crm_status"] != reconciled["erp_status"]
    reconciled["value_mismatch"] = reconciled["value_delta"].abs() > 100
    reconciled["requires_review"] = reconciled["status_mismatch"] | reconciled["value_mismatch"]
    return reconciled
