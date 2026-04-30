{% macro normalize_provider_name(col) -%}
  -- Lowercase, drop non-alphanumeric, strip common entity suffixes,
  -- collapse whitespace. Used for fuzzy-grouping service-provider
  -- names that lack a registry identifier (PCAOB / SEC #).
  trim(regexp_replace(
    regexp_replace(
      regexp_replace(
        lower(coalesce({{ col }}, '')),
        r'[^a-z0-9 ]', ' '
      ),
      r'\b(llc|llp|lp|lllp|inc|incorporated|corp|corporation|co|company|ltd|limited|plc|gmbh|ag|sa|nv|bv|partners|partnership|trust|the)\b',
      ''
    ),
    r'\s+', ' '
  ))
{%- endmacro %}
