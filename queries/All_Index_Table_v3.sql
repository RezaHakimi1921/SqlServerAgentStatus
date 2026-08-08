


Go


Declare @TABLENAME SYSNAME = 'dbo.BrandEventCustomerLogs';

Select
	  I.Name						  As IndexName
	, I.Is_Unique
	, IsNull(
	  String_Agg(
	  Case
	  When C.Is_Included_Column = 0 Then C.Column_Id End,
	  ','
	  ) Within Group (Order By C.Key_Ordinal),
	  ''
	  )								  As KeyColumnIds
	, IsNull(
	  String_Agg(
	  Case
	  When C.Is_Included_Column = 0 Then Col.Name End,
	  ','
	  ) Within Group (Order By C.Key_Ordinal),
	  ''
	  )								  As KeyColumns
	, IsNull(
	  String_Agg(
	  Case
	  When C.Is_Included_Column = 1 Then C.Column_Id End,
	  ','
	  ),
	  ''
	  )								  As IncludedColumnIds
	, IsNull(
	  String_Agg(
	  Case
	  When C.Is_Included_Column = 1 Then Col.Name End,
	  ','
	  ),
	  ''
	  )								  As IncludedColumns
	, IsNull(I.Filter_Definition, '') As Filter_Definition
From Sys.Indexes As I
	Join Sys.Index_Columns As C
		On I.Object_Id = C.Object_Id
			And I.Index_Id = C.Index_Id
	Join Sys.Columns As Col
		On Col.Object_Id = C.Object_Id
			And Col.Column_Id = C.Column_Id
Where
	  I.Object_Id = Object_Id(@TABLENAME)
	Group By I.Name
		   , I.Is_Unique
		   , I.Filter_Definition;






-- Unused Index Script
-- Original Author: Pinal Dave 
Select Top 25
	  O.Name									 As ObjectName
	, I.Name									 As IndexName
	, I.Index_Id								 As IndexId
	, Dm_Ius.User_Seeks							 As UserSeek
	, Dm_Ius.User_Scans							 As UsersCans
	, Dm_Ius.User_Lookups						 As UserLookups
	, Dm_Ius.User_Updates						 As UserUpdates
	, P.TableRows
	, 'DROP INDEX ' + QuoteName(I.Name)
	  + ' ON ' + QuoteName(S.Name) + '.'
	  + QuoteName(Object_Name(Dm_Ius.Object_Id)) As 'drop statement'
From Sys.Dm_Db_Index_Usage_Stats Dm_Ius
	Inner Join Sys.Indexes I
		On I.Index_Id = Dm_Ius.Index_Id
			And Dm_Ius.Object_Id = I.Object_Id
	Inner Join Sys.Objects O
		On Dm_Ius.Object_Id = O.Object_Id
	Inner Join Sys.ScHemAs S
		On O.Schema_Id = S.Schema_Id
	Inner Join (
		Select Sum(P.Rows) TableRows
			 , P.Index_Id
			 , P.Object_Id
		From Sys.Partitions P
		Group By P.Index_Id
			   , P.Object_Id) P
		On P.Index_Id = Dm_Ius.Index_Id
			And Dm_Ius.Object_Id = P.Object_Id
Where
	  ObjectProperty(Dm_Ius.Object_Id, 'IsUserTable') = 1
	  And Dm_Ius.Database_Id = Db_Id()
	  And I.Type_DeSc = 'nonclustered'
	  And I.Is_Primary_Key = 0
	  And I.Is_Unique_Constraint = 0
	  And Object_Name(O.[Object_Id]) = 'BrandEventCustomerLogs'

	--AND (dm_ius.user_seeks + dm_ius.user_scans + dm_ius.user_lookups) = 0
	Order By (Dm_Ius.User_Seeks + Dm_Ius.User_Scans + Dm_Ius.User_Lookups) Asc
Go





Select
	  Schema_Name(O.[Schema_Id])									  As [Schema Name]
	, Object_Name(S.[Object_Id])									  As [Table Name]
	, I.Name														  As [Index Name]
	, I.Index_Id
	, I.Is_Disabled
	, I.Is_Hypothetical
	, I.Has_Filter
	, I.Fill_Factor
	, S.User_Updates												  As [Total Writes]
	, S.User_Seeks + S.User_Scans + S.User_Lookups					  As [Total Reads]
	, S.User_Updates - (S.User_Seeks + S.User_Scans + S.User_Lookups) As [Difference]
From Sys.Dm_Db_Index_Usage_Stats As S With (Nolock)
	Inner Join Sys.Indexes As I With (Nolock)
		On S.[Object_Id] = I.[Object_Id]
			And I.Index_Id = S.Index_Id
	Inner Join Sys.Objects As O With (Nolock)
		On I.[Object_Id] = O.[Object_Id]
Where
	  ObjectProperty(S.[Object_Id], 'IsUserTable') = 1
	  And S.Database_Id = Db_Id()
	  And S.User_Updates > (S.User_Seeks + S.User_Scans + S.User_Lookups)
	  And I.Index_Id > 1 And I.[Type_DeSc] = N'NONCLUSTERED'
	  And I.Is_Primary_Key = 0 And I.Is_Unique_Constraint = 0 And I.Is_Unique = 0
	  And Object_Name(S.[Object_Id]) = 'BrandEventCustomerLogs'
	Order By [Difference] Desc
		   , [Total Writes] Desc
		   , [Total Reads] Asc
Option (Recompile);