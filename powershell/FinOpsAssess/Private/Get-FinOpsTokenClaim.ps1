function Get-FinOpsTokenClaim {
    <#
    .SYNOPSIS
        Decodes the claims payload of a JWT access token (no signature check).

    .DESCRIPTION
        Base64url-decodes the payload (second segment) of a three-part JWT
        and returns the claims as a [pscustomobject]. Used by the read-only
        scope guard to inspect the `aud`, `scp`, and `roles` claims of an
        access token.

    .PARAMETER AccessToken
        A JWT access token string (header.payload.signature).

    .OUTPUTS
        [pscustomobject] of the decoded claims.

    .NOTES
        NO SIGNATURE VERIFICATION BY DESIGN. This is a defense-in-depth
        scope gate (refuse-if-write) operating under an operator-misconfig
        threat model -- never an authentication or authorization primitive.
        An actor who controls the credential already controls the token, so
        forging a "read-only looking" token to defeat the guard is moot
        (they could simply not invoke the tool). Do NOT add brittle
        signature validation here, and do NOT remove this function as a
        "broken JWT library": claim introspection is its only job.
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param(
        [Parameter(Mandatory)]
        [string] $AccessToken
    )

    $segments = $AccessToken.Split('.')
    if ($segments.Count -ne 3) {
        throw "Access token is not a well-formed JWT (expected 3 dot-separated segments, found $($segments.Count))."
    }

    $payload = $segments[1]
    if ([string]::IsNullOrWhiteSpace($payload)) {
        throw 'Access token payload segment is empty.'
    }

    # base64url -> base64 with correct padding.
    $b64 = $payload.Replace('-', '+').Replace('_', '/')
    switch ($b64.Length % 4) {
        0 { break }
        2 { $b64 += '==' }
        3 { $b64 += '=' }
        default { throw 'Access token payload is not valid base64url (invalid length).' }
    }

    try {
        $bytes = [System.Convert]::FromBase64String($b64)
        $json = [System.Text.Encoding]::UTF8.GetString($bytes)
    } catch {
        throw "Failed to base64url-decode the access token payload: $($_.Exception.Message)"
    }

    try {
        $claims = $json | ConvertFrom-Json -ErrorAction Stop
    } catch {
        throw "Access token payload is not valid JSON: $($_.Exception.Message)"
    }

    if ($claims -isnot [pscustomobject]) {
        throw 'Access token payload did not decode to a JSON object.'
    }

    return $claims
}
