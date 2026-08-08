-- Add evidence_json for snapshot details on Today's Insights (dbo)
USE [SmartMonitorDB];
GO

IF COL_LENGTH(N'insight.insight_events', N'evidence_json') IS NULL
BEGIN
    ALTER TABLE insight.insight_events ADD evidence_json NVARCHAR(MAX) NULL;
END
GO
