-- ADO #{{TICKET_ID}} | DRY RUN — always rolls back
-- Cluster: {{CLUSTER}} | Target: {{TARGET_TABLE}}
-- No COMMIT line — rollback is structural.
-- CATCH always ROLLBACKs even when XACT_STATE() = 1.
-- Use RS1 output to populate rollback.sql tokens.

BEGIN
    BEGIN TRY
        SET XACT_ABORT ON;

        DECLARE @ustrCodeAuthor NVARCHAR(80) = N'{{AUTHOR_NAME}}';
        DECLARE @ustrAdHocBlock NVARCHAR(80) = N'{{TICKET_ID}}_{{CLUSTER}}_DRYRUN';

        BEGIN TRANSACTION;

        DECLARE @intAuthorPartyID INT = {{AUTHOR_PARTY_ID}};
        -- TODO: Declare target identifiers

        -- RS1: Pre-fix state (save for rollback.sql tokens)
        -- TODO: SELECT current values

        -- RS2: Invariant guard
        -- TODO: Verify preconditions

        -- Simulated fix (rolled back below)
        -- TODO: The actual UPDATE/INSERT

        -- RS3: Row count
        -- SELECT @@ROWCOUNT AS RowsUpdated;

        -- RS4: Post-fix verification
        -- TODO: SELECT updated values

        -- RS5: Gate summary — all gates must show PASS
        -- TODO: Build gate summary table

        ROLLBACK;
        PRINT N'DRY RUN COMPLETE — database unchanged.';
        SET XACT_ABORT OFF;

    END TRY
    BEGIN CATCH
        IF (XACT_STATE()) IN (-1, 1) BEGIN ROLLBACK TRANSACTION; SET XACT_ABORT OFF; END;

        INSERT INTO ERR.DB_EXCEPTION_TANK (
            [DatabaseName],[UserName],[CodeAuthor],[ErrorNumber],[ErrorState],
            [ErrorSeverity],[ErrorLine],[ErrorProcedure],[ErrorMessage],[ErrorDateTime])
        VALUES (
            DB_NAME(), ORIGINAL_LOGIN(), @ustrCodeAuthor, ERROR_NUMBER(), ERROR_STATE(),
            ERROR_SEVERITY(), ERROR_LINE(),
            ISNULL(ERROR_PROCEDURE(), CONCAT('AdhocBlock: ', @ustrAdHocBlock)),
            ERROR_MESSAGE(), GETDATE());

        THROW;
    END CATCH;

    IF @@TRANCOUNT > 0 ROLLBACK;
END;