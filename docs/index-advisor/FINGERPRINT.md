# MissingIndex Fingerprint — Algorithm (v1)

Canonical copy for Uni-Project docs. **Source of truth in product repo:**
`E:\SqlserverAgentProject\SqlServerAgentStatus\docs\index-advisor\FINGERPRINT.md`

## Summary

```text
fingerprint = SHA256_hex(
  lower(db) + "|" + lower(schema) + "|" + lower(table)
  + "|eq:" + join(eq_cols_preserve_order)
  + "|ineq:" + join(ineq_cols_preserve_order)
  + "|inc:" + join(sorted(inc_cols))
)
```

Column normalize: split on `,`, trim, strip `[]`, drop empty, lowercase.  
Equality/Inequality: **keep order**. Included: **sort**.
