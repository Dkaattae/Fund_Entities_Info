"""Form D primary_doc.xml parsing (ingestion/form-d/parse_xml_schema.py).

The fixture is a real SEC filing (Lexaria Bioscience, 2025). get_metadata
hits data.sec.gov, so it is stubbed out.
"""

import numpy as np
import pandas as pd
import pytest

from conftest import load_module

parser = load_module("ingestion/form-d/parse_xml_schema.py", "parse_xml_schema")

ACCESSION = "0001348362-25-000001"


def _values(series):
    """Series -> list with missing values as None (pandas 3 stores None as
    NaN in string Series; both load to BigQuery as NULL)."""
    return [None if pd.isna(v) else v for v in series.tolist()]


METADATA = {
    "file_number": "021-123456",
    "filing_date": "2025-10-01",
    "sic_code": "2834",
}


@pytest.fixture
def no_network(monkeypatch):
    monkeypatch.setattr(parser, "get_metadata", lambda cik, acc: METADATA)


@pytest.fixture
def parsed(no_network, fixtures_dir):
    xml = (fixtures_dir / "form_d_primary_doc.xml").read_bytes()
    return parser.parse_formd_xml(xml, "0001348362", ACCESSION)


def test_submission(parsed):
    assert parsed["formd_submission"] == {
        "accessionnumber": ACCESSION,
        "file_num": "021-123456",
        "filing_date": "2025-10-01",
        "sic_code": "2834",
        "schemaversion": "X0708",
        "submissiontype": "D",
        "testorlive": "LIVE",
    }


def test_submission_without_metadata(monkeypatch, fixtures_dir):
    monkeypatch.setattr(parser, "get_metadata", lambda cik, acc: None)
    xml = (fixtures_dir / "form_d_primary_doc.xml").read_bytes()
    sub = parser.parse_formd_xml(xml, "0001348362", ACCESSION)["formd_submission"]
    assert sub["file_num"] == "" and sub["filing_date"] == ""


def test_issuer(parsed):
    [issuer] = parsed["issuer_dict"]
    assert issuer["entityname"] == "Lexaria Bioscience Corp."
    assert issuer["jurisdictionofinc"] == "NEVADA"
    assert issuer["stateorcountry"] == "A1"
    assert issuer["is_primaryissuer_flag"] is True
    assert issuer["issuer_seq_key"] == 1
    assert issuer["yearofinc_timespan_choice"] == "Five Years Ago or More"
    assert issuer["edgar_previousname_1"] == "LEXARIA CORP."
    assert issuer["edgar_previousname_2"] == "Lexaria Corp."
    assert pd.isna(issuer["edgar_previousname_3"])
    # raw nested columns are dropped after being flattened
    assert not any(k.startswith("yearOfInc.") for k in issuer)
    assert "edgarPreviousNameList.previousName" not in issuer


def test_related_persons(parsed):
    people = parsed["related_person_dict_list"]
    assert len(people) == 8
    assert [p["relatedperson_seq_key"] for p in people] == list(range(1, 9))
    docherty = people[1]
    assert (docherty["firstname"], docherty["lastname"]) == ("John", "Docherty")
    assert docherty["relationship_1"] == "Executive Officer"
    assert docherty["relationship_2"] == "Director"
    assert pd.isna(docherty["relationship_3"])
    assert people[5]["middlename"] == "Edward"


def test_recipients(parsed):
    [recipient] = parsed["recipient_dict_list"]
    assert recipient["recipientname"] == "H.C. WAINWRIGHT & CO."
    assert recipient["recipientcrdnumber"] == "375"
    assert recipient["states_or_value_list"] == ["IL", "NY"]
    assert recipient["recipient_seq_key"] == 1


def test_signatures_single_signature_is_listified(parsed):
    [sig] = parsed["signature_dict_list"]
    assert sig["nameofsigner"] == "Richard Christopher"
    assert sig["signaturetitle"] == "CEO"
    assert sig["accessionnumber"] == ACCESSION


def test_offering(parsed):
    [offering] = parsed["offering_dict_list"]
    assert offering["accessionnumber"] == ACCESSION
    assert offering["industrygrouptype"] == "Biotechnology"
    assert offering["totalofferingamount"] == "4000000"
    assert offering["totalamountsold"] == "4000000"
    assert offering["sale_date"] == "2025-09-29"
    assert offering["isamendment"] == "false"
    assert offering["salescomm_dollaramount"] == "280000"
    # recipients / signatures live in their own tables, not the offering row
    assert not any(k.startswith(("salescompensationlist", "signatureblock")) for k in offering)
    # every column is lower-case / BigQuery-safe
    assert all(k == k.lower() and "." not in k for k in offering)


MINIMAL_XML = b"""<?xml version="1.0"?>
<edgarSubmission>
  <schemaVersion>X0708</schemaVersion>
  <submissionType>D/A</submissionType>
  <testOrLive>LIVE</testOrLive>
  <primaryIssuer>
    <entityName>Tiny Fund LP</entityName>
    <yearOfInc><withinFiveYears>true</withinFiveYears><value>2024</value></yearOfInc>
  </primaryIssuer>
  <coIssuerList>
    <coIssuerInfo><entityName>Tiny Fund GP LLC</entityName>
      <yearOfInc><yetToBeFormed>true</yetToBeFormed></yearOfInc></coIssuerInfo>
  </coIssuerList>
  <relatedPersonsList>
    <relatedPersonInfo>
      <relatedPersonName><firstName>Solo</firstName><lastName>Person</lastName></relatedPersonName>
      <relatedPersonRelationshipList><relationship>Promoter</relationship></relatedPersonRelationshipList>
    </relatedPersonInfo>
  </relatedPersonsList>
</edgarSubmission>
"""


def test_minimal_filing_with_missing_sections(no_network):
    out = parser.parse_formd_xml(MINIMAL_XML, "1", "0000000001-26-000001")
    assert out["formd_submission"]["submissiontype"] == "D/A"
    primary, co = out["issuer_dict"]
    assert primary["is_primaryissuer_flag"] is True and co["is_primaryissuer_flag"] is False
    assert [primary["issuer_seq_key"], co["issuer_seq_key"]] == [1, 2]
    assert primary["yearofinc_timespan_choice"] == "Within Last Five Years"
    assert primary["yearofinc_value_entered"] == "2024"
    assert co["yearofinc_timespan_choice"] == "Yet to be formed"
    # a single relatedPersonInfo (dict, not list) still yields one row
    [person] = out["related_person_dict_list"]
    assert person["relationship_1"] == "Promoter"
    # absent sections degrade to empty lists / a bare offering row
    assert out["signature_dict_list"] == []
    assert out["recipient_dict_list"] == []
    assert out["offering_dict_list"] == [{"accessionnumber": "0000000001-26-000001"}]


@pytest.mark.parametrize("val, expected", [
    ("Only", ["Only", None, None]),
    (["a", "b"], ["a", "b", None]),
    (["a", "b", "c", "d"], ["a", "b", "c"]),   # capped at 3
    (None, [None, None, None]),
    (np.nan, [None, None, None]),
    (42, [None, None, None]),
])
def test_split_names(val, expected):
    assert _values(parser.split_names(val)) == expected


@pytest.mark.parametrize("row, expected", [
    ({"yearOfInc.overFiveYears": "true"}, ["Five Years Ago or More", None]),
    ({"yearOfInc.yetToBeFormed": "true"}, ["Yet to be formed", None]),
    ({"yearOfInc.withinFiveYears": "true", "yearOfInc.value": "2023"}, ["Within Last Five Years", "2023"]),
    ({"yearOfInc.withinLastFiveYears": "2022"}, ["Within Last Five Years", "2022"]),
    ({}, [None, None]),
])
def test_map_year_of_inc(row, expected):
    assert _values(parser.map_year_of_inc(pd.Series(row, dtype=object))) == expected


def test_get_xml_url():
    assert parser.get_xml_url(1348362, "000134836225000001") == (
        "https://www.sec.gov/Archives/edgar/data/1348362/000134836225000001/primary_doc.xml"
    )
