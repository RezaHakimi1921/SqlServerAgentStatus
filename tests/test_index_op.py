"""Parse CREATE / REBUILD / REORGANIZE index statements."""
from modules.activity.layout import extract_index_op, _command_action_tag


CREATE_IX = """
CREATE NONCLUSTERED INDEX IX_CA_CustomerClubId_Credit
ON dbo.CustomerActivities (CustomerClubId)
INCLUDE (Credit, RemainingCreditAfterUsed, Expired)
WITH (ONLINE = ON, MAXDOP = 4)
"""


def test_create_nonclustered_index():
    ix = extract_index_op(CREATE_IX)
    assert ix is not None
    assert ix["op"] == "create"
    assert ix["action_label"] == "CREATE INDEX"
    assert ix["kind"] == "NONCLUSTERED"
    assert ix["index_name"].upper() == "IX_CA_CUSTOMERCLUBID_CREDIT"
    assert ix["table"].lower() == "dbo.customeractivities"
    assert "CustomerClubId" in ix["columns"]
    assert "Credit" in ix["include"]
    assert ix["options"].get("ONLINE", "").upper() == "ON"
    assert ix["options"].get("MAXDOP") == "4"
    assert any("ONLINE" in c for c in ix["option_chips"])
    assert any("MAXDOP" in c for c in ix["option_chips"])


def test_action_tag_says_create_index_not_bare_create():
    tag = _command_action_tag("CREATE", CREATE_IX, is_head=False)
    chip = tag.children[0]
    assert "CREATE INDEX" in str(chip.children).upper()


def test_alter_index_rebuild():
    sql = "ALTER INDEX IX_X ON dbo.T REBUILD WITH (ONLINE = ON, MAXDOP = 2)"
    ix = extract_index_op(sql)
    assert ix["op"] == "rebuild"
    assert ix["action_label"] == "INDEX REBUILD"
    assert ix["options"].get("MAXDOP") == "2"


def test_alter_index_reorganize():
    sql = "ALTER INDEX ALL ON dbo.Orders REORGANIZE"
    ix = extract_index_op(sql)
    assert ix["op"] == "reorganize"
    assert ix["action_label"] == "INDEX REORGANIZE"
    assert ix["index_name"].upper() == "ALL"
