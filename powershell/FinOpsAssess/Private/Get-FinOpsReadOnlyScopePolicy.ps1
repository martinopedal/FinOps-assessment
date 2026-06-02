function Get-FinOpsReadOnlyScopePolicy {
    <#
    .SYNOPSIS
        Returns the read-only scope-classification policy for the sec.9 guard.

    .DESCRIPTION
        Single source of truth for the runtime read-only scope guard
        (docs/plan.md sec.4.1 / sec.1.7a criterion 9). Emits the regex patterns
        used to classify an individual OAuth scope / app-role / token claim
        as a WRITE grant (must refuse), a READ grant (allowed), or leaves it
        UNKNOWN (fail-closed by default).

        This is deliberately the ONLY file in the module that contains the
        literal forbidden patterns (e.g. ".ReadWrite."): every other module
        file is scanned by the read-only tripwire test, which excludes this
        one file by name. A counter-assertion in the test suite proves no
        other file reintroduces those literals.

        Classification is PATTERN-based, not allow-list-based, for the WRITE
        decision: a novel or renamed write scope still matches a write
        pattern (".Write", ".ReadWrite.", ".Manage", etc.) and is refused.
        The READ patterns only ever ALLOW; they never override a WRITE match.

    .NOTES
        WRITE patterns win over READ patterns. Surface routing is by the
        token's `aud` claim (see Test-FinOpsReadOnlyScope). Azure Resource
        Manager (ARM) write capability is RBAC-side and NOT visible in token
        claims, so ARM tokens are reported as claim-insufficient and refused
        by default until the Phase-6 collectors add RBAC introspection.
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param()

    # Surface-agnostic WRITE detectors. Any scope/role/claim string matching
    # one of these is a write/admin grant and MUST cause the guard to refuse.
    $writePatterns = @(
        # Microsoft Graph / Entra delegated + application permissions.
        '\.ReadWrite(\.|$)',          # User.ReadWrite.All, Directory.ReadWrite.All
        '\.Write(\.|$)',              # *.Write
        '\.Manage(\.|$)',             # *.Manage, *.ManageAsApp
        'ManageAsApp',
        '\.AccessAsUser\.All',        # full directory write under user RBAC (no "Write" token)
        '\.Send(\.|$)',               # Mail.Send, ChannelMessage.Send, Chat.Send
        '\.Invite(\.|$)',             # User.Invite.All
        '\.Create(\.|$)',             # *.Create
        '\.Delete(\.|$)',             # *.Delete
        '^full_access_as_app$',       # EWS/Exchange full mailbox access
        # GitHub classic OAuth scopes (write/admin shaped).
        '^repo$',                     # full control of private repos (write)
        '^write:',                    # write:org, write:packages, ...
        '^admin:',                    # admin:org, admin:repo_hook, ...
        '^delete:',                   # delete:packages, delete_repo
        '^delete_repo$',
        '^workflow$',                 # update GitHub Actions workflows
        '^user$',                     # write profile data
        '^gist$',                     # write gists
        '^codespace$',                # manage codespaces
        '^project$',                  # write projects
        # Azure DevOps (vso.*) write/manage/execute/publish families.
        '_write(\b|$)',
        '_manage(\b|$)',
        '_execute(\b|$)',
        '_publish(\b|$)',
        '_full(\b|$)',
        # Azure DevOps bare scopes that are inherently administrative even
        # without a write suffix (ADO convention: bare vso.X is otherwise a
        # read scope; these are the named exceptions).
        '^vso\.tokenadministration$',
        '^vso\.tokens$',
        '^vso\.governance$',
        # Azure Resource Manager delegated user-impersonation (write-capable;
        # actual read/write is RBAC-side -- see ARM handling in the classifier).
        '^user_impersonation$'
    )

    # Surface-agnostic READ allowlist. These only ALLOW; a string that also
    # matches a WRITE pattern is still classified WRITE.
    $readPatterns = @(
        '\.Read(\.|$)',               # *.Read, *.Read.All
        '^read:',                     # GitHub read:org, read:packages, ...
        ':read$',                     # fine-grained-ish read suffix
        '_read(\b|$)',                # ADO vso.*_read
        # ADO convention: a bare vso.<area> scope (no write/manage/execute/
        # publish/full suffix) is a read scope. Write variants are already
        # caught above and win; named administrative bare scopes are denied
        # above too. WRITE patterns are evaluated first, so this only ever
        # reaches genuinely read-shaped bare scopes.
        '^vso\.[a-z]+$',
        '^public_repo$',              # GitHub read of public repos (no write)
        '^repo:status$',              # commit status read
        '^openid$', '^profile$', '^email$', '^offline_access$'  # OIDC, non-resource
    )

    # Token `aud` (audience) values mapped to a logical surface. ARM is
    # called out separately because its write capability is not in claims.
    $audienceSurfaces = @(
        [pscustomobject]@{ Surface = 'Graph'; Patterns = @('graph\.microsoft\.com', '^00000003-0000-0000-c000-000000000000$') }
        [pscustomobject]@{ Surface = 'AzureResourceManager'; Patterns = @('management\.azure\.com', 'management\.core\.windows\.net', '^https://management\.') }
        [pscustomobject]@{ Surface = 'AzureDevOps'; Patterns = @('499b84ac-1321-427f-aa17-267ca6975798', 'visualstudio\.com', 'dev\.azure\.com') }
    )

    # Token-shaped strings that are NOT scopes (someone passed a credential
    # to -Scope by mistake, or a fine-grained PAT whose perms we cannot see).
    # Treated as UNKNOWN -> fail-closed.
    $opaqueTokenPrefixes = @('github_pat_', 'ghp_', 'gho_', 'ghu_', 'ghs_', 'ghr_')

    [pscustomobject]@{
        WritePatterns       = $writePatterns
        ReadPatterns        = $readPatterns
        AudienceSurfaces    = $audienceSurfaces
        OpaqueTokenPrefixes = $opaqueTokenPrefixes
    }
}
