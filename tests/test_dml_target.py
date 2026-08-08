"""Parse DML target table from statement text."""
from modules.activity.layout import extract_dml_target, _command_action_tag


SAMPLE = """
BEGIN
    UPDATE TOP (@BatchSize) f
    SET BranchCloudConsumerId = @newLocknumber
    FROM dbo.FACTURE f
    WHERE f.BranchCloudConsumerId = @oldLocknumber
    AND NOT EXISTS (
        SELECT 1
        FROM dbo.FACTURE f2
        WHERE f2.OrginalId = f.OrginalId
        AND f2.BranchCloudConsumerId = @newLocknumber
    );
END
"""

THREE_PART = """
UPDATE TOP (@BatchSize) cfc
SET BranchCloudConsumerId = @newLocknumber
FROM SmartwifiCustomerClub.dbo.CustomerFactureClubs cfc
WHERE cfc.BranchCloudConsumerId = @oldLocknumber
"""


def test_update_from_alias_resolves_facture():
    t = extract_dml_target(SAMPLE)
    assert t is not None
    assert t["verb"] == "UPDATE"
    assert t["table"].upper() == "DBO.FACTURE"
    assert t["table_short"].upper() == "FACTURE"


def test_three_part_name_not_truncated_to_schema():
    t = extract_dml_target(THREE_PART)
    assert t is not None
    assert t["table"].lower() == "smartwificustomerclub.dbo.customerfactureclubs"
    assert t["table_short"].lower() == "customerfactureclubs"


def test_rejects_schema_only_capture():
    # Would previously return SmartwifiCustomerClub.dbo
    bad = "UPDATE TOP (1) x SET a=1 FROM SmartwifiCustomerClub.dbo"
    t = extract_dml_target(bad)
    assert t is None or t["table_short"].lower() != "dbo"


def test_update_direct_table():
    t = extract_dml_target("UPDATE dbo.Orders SET x = 1 WHERE id = 2")
    assert t["verb"] == "UPDATE"
    assert t["table"] == "dbo.Orders"
    assert t["table_short"] == "Orders"


def test_insert_into():
    t = extract_dml_target("INSERT INTO [sales].[Invoice] (a) VALUES (1)")
    assert t["verb"] == "INSERT"
    assert t["table"].lower() == "sales.invoice"


def test_action_tag_uses_short_name():
    tag = _command_action_tag("EXECUTE", THREE_PART, is_head=False)
    chip = tag.children[0]
    label = str(chip.children).upper()
    assert "CUSTOMERFACTURECLUBS" in label
    assert "SMARTWIFICUSTOMERCLUB.DBO" not in label or "CUSTOMERFACTURECLUBS" in label
