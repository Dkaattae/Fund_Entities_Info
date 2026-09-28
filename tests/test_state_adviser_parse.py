"""IA_FIRM_STATE XML feed parsing (ingestion/adv-form/state_adviser_parse.py)."""

import pytest

from conftest import load_module

state_parse = load_module("ingestion/adv-form/state_adviser_parse.py", "state_adviser_parse")

FEED = """<?xml version="1.0" encoding="UTF-8"?>
<IAPDFirmSECReport GenOn="2026-09-27">
  <Firms>
    <Firm>
      <Info FirmCrdNb="111" BusNm="Full Advisers" LegalNm="Full Advisers LLC" UmbrRgstn="N"/>
      <MainAddr Strt1="1 Main St" City="Austin" State="TX" Cntry="United States" PostlCd="78701" PhNb="555"/>
      <Filing Dt="2026-09-01" FormVrsn="10/2021"/>
      <FormInfo><Part1A>
        <Item1><WebAddrs><WebAddr>https://a.example</WebAddr><WebAddr>https://b.example</WebAddr></WebAddrs></Item1>
        <Item3A OrgFormNm="Limited Liability Company"/>
        <Item3B Q3B="December"/>
        <Item3C StateCD="TX" CntryNm="United States"/>
        <Item5A TtlEmp="4"/>
        <Item5F Q5F2A="1000" Q5F2B="50" Q5F2C="1050" Q5F2F="12"/>
      </Part1A></FormInfo>
      <StateRgstn><Rgltrs>
        <Rgltr Cd="TX" St="APPROVED" Dt="2026-08-15"/>
        <Rgltr Cd="OK" St="PENDING" Dt="2026-09-02"/>
      </Rgltrs></StateRgstn>
      <ERA><Rgltrs><Rgltr Cd="CA" St="APPROVED" Dt="2025-01-01"/></Rgltrs></ERA>
    </Firm>
    <Firm>
      <Info FirmCrdNb="222" BusNm="Bare Firm"/>
    </Firm>
    <Firm>
      <MainAddr City="Nowhere"/>
    </Firm>
  </Firms>
</IAPDFirmSECReport>
"""


@pytest.fixture
def parsed(tmp_path):
    path = tmp_path / "feed.xml"
    path.write_text(FEED)
    return state_parse.parse_xml(str(path))


def test_firms(parsed):
    firms, _ = parsed
    # the <Firm> without <Info> is skipped
    assert firms["firm_crd"].tolist() == ["111", "222"]
    full = firms.iloc[0]
    assert full["legal_name"] == "Full Advisers LLC"
    assert full["main_city"] == "Austin"
    assert full["filing_date"] == "2026-09-01"
    assert full["org_form"] == "Limited Liability Company"
    assert full["fiscal_year_end"] == "December"
    assert full["aum_total"] == "1050"
    assert full["websites"] == "https://a.example; https://b.example"
    assert (firms["snapshot_date"] == "2026-09-27").all()


def test_sparse_firm_gets_empty_strings_not_nan(parsed):
    firms, _ = parsed
    bare = firms.iloc[1]
    for col in ["main_city", "filing_date", "aum_total", "websites", "org_form", "legal_name"]:
        assert bare[col] == ""


def test_registrations(parsed):
    _, regs = parsed
    rows = regs[["firm_crd", "regulator_state", "registration_status", "registration_type"]]
    assert rows.values.tolist() == [
        ["111", "TX", "APPROVED", "STATE"],
        ["111", "OK", "PENDING", "STATE"],
        ["111", "CA", "APPROVED", "ERA"],
    ]
    assert (regs["snapshot_date"] == "2026-09-27").all()
