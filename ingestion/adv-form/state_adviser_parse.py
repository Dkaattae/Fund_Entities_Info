"""Parse the IA_FIRM_STATE XML feed into flat DataFrames."""

import xml.etree.ElementTree as ET
import pandas as pd


def _attr(element, *names):
    """Return a dict of named attributes from an element (empty string for missing)."""
    return {name: (element.get(name) or "") for name in names}


def parse_xml(xml_path: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Parse IA_FIRM_STATE XML into (firms_df, registrations_df).

    firms_df: one row per firm with core info, address, filing, and key form fields.
    registrations_df: one row per firm per state registration.
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()
    gen_date = root.get("GenOn", "")

    firms = []
    registrations = []

    for firm in root.iter("Firm"):
        info = firm.find("Info")
        if info is None:
            continue
        crd = info.get("FirmCrdNb", "")
        firm_row = {
            "firm_crd": crd,
            "business_name": info.get("BusNm", ""),
            "legal_name": info.get("LegalNm", ""),
            "umbrella_registration": info.get("UmbrRgstn", ""),
        }

        # Main address
        addr = firm.find("MainAddr")
        if addr is not None:
            firm_row.update({
                "main_street1": addr.get("Strt1", ""),
                "main_street2": addr.get("Strt2", ""),
                "main_city": addr.get("City", ""),
                "main_state": addr.get("State", ""),
                "main_country": addr.get("Cntry", ""),
                "main_postal_code": addr.get("PostlCd", ""),
                "main_phone": addr.get("PhNb", ""),
            })

        # Filing info
        filing = firm.find("Filing")
        if filing is not None:
            firm_row["filing_date"] = filing.get("Dt", "")
            firm_row["form_version"] = filing.get("FormVrsn", "")

        # Key Part1A fields
        form_info = firm.find("FormInfo")
        if form_info is not None:
            part1a = form_info.find("Part1A")
            if part1a is not None:
                item3a = part1a.find("Item3A")
                if item3a is not None:
                    firm_row["org_form"] = item3a.get("OrgFormNm", "")

                item3b = part1a.find("Item3B")
                if item3b is not None:
                    firm_row["fiscal_year_end"] = item3b.get("Q3B", "")

                item3c = part1a.find("Item3C")
                if item3c is not None:
                    firm_row["state_of_org"] = item3c.get("StateCD", "")
                    firm_row["country_of_org"] = item3c.get("CntryNm", "")

                item5a = part1a.find("Item5A")
                if item5a is not None:
                    firm_row["total_employees"] = item5a.get("TtlEmp", "")

                item5f = part1a.find("Item5F")
                if item5f is not None:
                    firm_row["aum_discretionary"] = item5f.get("Q5F2A", "")
                    firm_row["aum_non_discretionary"] = item5f.get("Q5F2B", "")
                    firm_row["aum_total"] = item5f.get("Q5F2C", "")
                    firm_row["account_count"] = item5f.get("Q5F2F", "")

                # Websites
                item1 = part1a.find("Item1")
                if item1 is not None:
                    web_addrs = item1.find("WebAddrs")
                    if web_addrs is not None:
                        urls = [w.text for w in web_addrs.findall("WebAddr") if w.text]
                        firm_row["websites"] = "; ".join(urls)

        firm_row["snapshot_date"] = gen_date
        firms.append(firm_row)

        # State registrations
        state_rgstn = firm.find("StateRgstn")
        if state_rgstn is not None:
            for rgltr in state_rgstn.iter("Rgltr"):
                registrations.append({
                    "firm_crd": crd,
                    "regulator_state": rgltr.get("Cd", ""),
                    "registration_status": rgltr.get("St", ""),
                    "registration_date": rgltr.get("Dt", ""),
                    "registration_type": "STATE",
                    "snapshot_date": gen_date,
                })

        # ERA registrations
        era = firm.find("ERA")
        if era is not None:
            for rgltr in era.iter("Rgltr"):
                registrations.append({
                    "firm_crd": crd,
                    "regulator_state": rgltr.get("Cd", ""),
                    "registration_status": rgltr.get("St", ""),
                    "registration_date": rgltr.get("Dt", ""),
                    "registration_type": "ERA",
                    "snapshot_date": gen_date,
                })

    firms_df = pd.DataFrame(firms)
    registrations_df = pd.DataFrame(registrations)

    # Fill missing columns that may not appear in every firm
    for col in ["main_street1", "main_street2", "main_city", "main_state",
                "main_country", "main_postal_code", "main_phone",
                "filing_date", "form_version", "org_form", "fiscal_year_end",
                "state_of_org", "country_of_org", "total_employees",
                "aum_discretionary", "aum_non_discretionary", "aum_total",
                "account_count", "websites"]:
        if col not in firms_df.columns:
            firms_df[col] = ""

    firms_df = firms_df.fillna("")
    registrations_df = registrations_df.fillna("")

    return firms_df, registrations_df


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/ia_state_test.xml"
    firms_df, reg_df = parse_xml(path)
    print(f"Firms: {firms_df.shape}")
    print(firms_df.head())
    print(f"\nRegistrations: {reg_df.shape}")
    print(reg_df.head())
