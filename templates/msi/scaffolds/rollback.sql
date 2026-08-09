-- ADO #{{TICKET_ID}} | ROLLBACK
-- Restores prior values from dryrun RS1.
-- All values below MUST be populated from dryrun output.
-- Default: ROLLBACK active, COMMIT commented out.

BEGIN
    BEGIN TRY
        SET XACT_ABORT ON;

        DECLARE @ustrCodeAuthor NVARCHAR(80) = N'{{AUTHOR_NAME}}';
        DECLARE @ustrAdHocBlock NVARCHAR(80) = N'{{TICKET_ID}}_{{CLUSTER}}_ROLLBACK';

        BEGIN TRANSACTION;

        DECLARE @intAuthorPartyID INT = {{AUTHOR_PARTY_ID}};
        -- TODO: Declare targets
        -- TODO: Hardcode prior values from dryrun RS1

        -- COMMIT TRANSACTION;
        ROLLBACK TRANSACTION;
        SET XACT_ABORT OFF;

    END TRY
    BEGIN CATCH
        IF (XACT_STATE()) = -1 BEGIN ROLLBACK TRANSACTION; SET XACT_ABORT OFF; END;
        IF (XACT_STATE()) =  1 BEGIN COMMIT TRANSACTION;   SET XACT_ABORT OFF; END;

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
