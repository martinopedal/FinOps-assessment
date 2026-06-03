Set-StrictMode -Version Latest

# Faithful, version-portable JSON reader for finops-assess report files.
#
# Native ``ConvertFrom-Json`` coerces ISO-8601 timestamp strings (such as
# ``run.generated_at``) into ``[datetime]`` objects. The ``-DateKind String``
# switch disables that, but it only exists on PowerShell 7.5+, so relying on
# it breaks on the 7.4 runtime used in CI. To stay byte-identical to the
# Python ``json.loads`` semantics on every supported PowerShell version we
# parse with ``System.Text.Json`` and keep every JSON scalar as its literal
# type (strings stay strings, no date coercion).

function ConvertFrom-FinOpsReportJsonElement {
    [CmdletBinding()]
    [OutputType([object])]
    param([Parameter(Mandatory)] [System.Text.Json.JsonElement] $Element)

    switch ($Element.ValueKind) {
        ([System.Text.Json.JsonValueKind]::Object) {
            $object = [ordered]@{}
            foreach ($property in $Element.EnumerateObject()) {
                $object[$property.Name] = ConvertFrom-FinOpsReportJsonElement -Element $property.Value
            }
            return [pscustomobject] $object
        }
        ([System.Text.Json.JsonValueKind]::Array) {
            $items = [System.Collections.Generic.List[object]]::new()
            foreach ($child in $Element.EnumerateArray()) {
                [void] $items.Add((ConvertFrom-FinOpsReportJsonElement -Element $child))
            }
            # Unary comma defeats PowerShell's single-element array unwrapping on
            # return, so a JSON array of length 1 stays an array (matching json.loads).
            return , ([object[]] $items.ToArray())
        }
        ([System.Text.Json.JsonValueKind]::String) {
            return $Element.GetString()
        }
        ([System.Text.Json.JsonValueKind]::Number) {
            $raw = $Element.GetRawText()
            if ($raw.IndexOfAny([char[]]@('.', 'e', 'E')) -ge 0) {
                return [double] $Element.GetDouble()
            }
            $asLong = [long] 0
            if ($Element.TryGetInt64([ref] $asLong)) {
                return $asLong
            }
            return [double] $Element.GetDouble()
        }
        ([System.Text.Json.JsonValueKind]::True) { return $true }
        ([System.Text.Json.JsonValueKind]::False) { return $false }
        ([System.Text.Json.JsonValueKind]::Null) { return $null }
        default { return $null }
    }
}

function ConvertFrom-FinOpsReportJson {
    [CmdletBinding()]
    [OutputType([object])]
    param([Parameter(Mandatory)] [AllowEmptyString()] [string] $Json)

    $document = [System.Text.Json.JsonDocument]::Parse($Json)
    try {
        return ConvertFrom-FinOpsReportJsonElement -Element $document.RootElement
    } finally {
        $document.Dispose()
    }
}
