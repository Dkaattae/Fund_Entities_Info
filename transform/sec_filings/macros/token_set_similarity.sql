{% macro token_set_similarity(a, b) -%}
  -- Token-set (Jaccard) similarity between two already-normalized strings.
  -- Returns |tokens(a) ∩ tokens(b)| / |tokens(a) ∪ tokens(b)| in [0, 1].
  -- Word-order independent, so "NAV FUND SERVICES" and "FUND SERVICES NAV"
  -- score 1.0 — which raw Levenshtein (EDIT_DISTANCE) would not.
  -- Inputs should be lower-cased / punctuation-stripped first
  -- (e.g. via normalize_provider_name) so tokens align.
  safe_divide(
    (
      select count(distinct tok)
      from unnest(split({{ a }}, ' ')) tok
      where tok != ''
        and tok in (select x from unnest(split({{ b }}, ' ')) x where x != '')
    ),
    (
      select count(distinct tok)
      from unnest(array_concat(split({{ a }}, ' '), split({{ b }}, ' '))) tok
      where tok != ''
    )
  )
{%- endmacro %}
