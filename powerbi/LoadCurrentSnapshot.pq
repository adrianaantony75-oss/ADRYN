// Create a text parameter OutputRoot, e.g. D:\ADRYN\outputs.
// Save this query as LoadCurrentSnapshot, then call it with a CSV base name.
(TableName as text) as table =>
let
    Manifest = Json.Document(File.Contents(OutputRoot & "\current_run.json")),
    RunId = Manifest[run_id],
    FilePath = OutputRoot & "\snapshots\" & RunId & "\" & TableName & ".csv",
    Source = Csv.Document(File.Contents(FilePath), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars=true])
in
    Headers
