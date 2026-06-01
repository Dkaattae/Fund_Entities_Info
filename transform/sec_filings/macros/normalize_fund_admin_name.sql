{% macro normalize_fund_admin_name(col) -%}
  -- Aggressive normalization for FUND_ADMIN names only.
  -- Strips entity types, jurisdiction words, and generic fund-industry words so that
  -- "NAV FUND SERVICES CAYMAN LTD." and "NAV Fund Services" both normalize to "nav".
  -- Used to match filing raw_names against seed canonical_names without requiring
  -- an exact string entry for every international office variant.
  trim(regexp_replace(
    regexp_replace(
      regexp_replace(
        regexp_replace(
          regexp_replace(
            lower(coalesce({{ col }}, '')),
            r'[^a-z0-9 ]', ' '
          ),
          r'\b(llc|llp|lp|lllp|inc|incorporated|corp|corporation|co|company|ltd|limited|plc|gmbh|ag|sa|nv|bv|pte|pty|sarl|srl|sdn|bhd|partners|partnership|trust|the)\b',
          ''
        ),
        r'\b(cayman|islands|luxembourg|ireland|singapore|guernsey|jersey|mauritius|bermuda|offshore|hong|kong|hk|asia|asian|europe|european|uk|americas)\b',
        ''
      ),
      r'\b(fund|funds|services|service|administration|administrative|administrators|financial|finance|management|managers|alternative|asset|assets|corporate|group|international|global|bank|branch|technologies|technology)\b',
      ''
    ),
    r'\s+', ' '
  ))
{%- endmacro %}
