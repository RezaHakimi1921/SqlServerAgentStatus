import unittest

from collectors.sqlserver_collector import SqlServerCollector, SqlServerCollectorConfig


class CollectorShapeTests(unittest.TestCase):
    def setUp(self):
        self.collector = SqlServerCollector(
            SqlServerCollectorConfig(instance_id="test-instance", database_name="TestDb"),
            connection_factory=lambda: None,
        )

    def test_index_columns_are_ordered_and_include_columns_separated(self):
        rows = [
            self._row(column_name="Included", key_ordinal=0, is_included_column=True,
                      is_descending_key=False),
            self._row(column_name="SecondKey", key_ordinal=2, is_included_column=False,
                      is_descending_key=True),
            self._row(column_name="FirstKey", key_ordinal=1, is_included_column=False,
                      is_descending_key=False),
        ]

        [index] = self.collector._shape_index_rows(rows, "2026-11-16T00:00:00+00:00")

        self.assertEqual(
            index["key_columns"],
            [
                {"ordinal": 1, "name": "FirstKey", "descending": False},
                {"ordinal": 2, "name": "SecondKey", "descending": True},
            ],
        )
        self.assertEqual(index["included_columns"], ["Included"])
        self.assertEqual(index["used_bytes"], 5 * 8192)
        self.assertEqual(index["reserved_bytes"], 8 * 8192)
        self.assertEqual(index["instance_id"], "test-instance")

    def test_index_without_column_metadata_is_still_represented(self):
        [index] = self.collector._shape_index_rows(
            [self._row(column_name=None, key_ordinal=None, is_included_column=None,
                       is_descending_key=None)],
            "2026-11-16T00:00:00+00:00",
        )
        self.assertEqual(index["key_columns"], [])
        self.assertEqual(index["included_columns"], [])

    def test_integer_conversion_preserves_unknown_as_none(self):
        self.assertIsNone(self.collector._to_int(None))
        self.assertEqual(self.collector._to_int(42), 42)

    @staticmethod
    def _row(**overrides):
        row = {
            "database_name": "TestDb",
            "schema_name": "dbo",
            "table_name": "Orders",
            "object_id": 100,
            "index_id": 2,
            "index_name": "IX_Orders_Test",
            "index_type": "NONCLUSTERED",
            "is_unique": False,
            "is_primary_key": False,
            "is_unique_constraint": False,
            "is_disabled": False,
            "has_filter": False,
            "filter_definition": None,
            "key_ordinal": 1,
            "is_included_column": False,
            "is_descending_key": False,
            "column_name": "OrderId",
            "used_pages": 5,
            "reserved_pages": 8,
        }
        row.update(overrides)
        return row


if __name__ == "__main__":
    unittest.main()
