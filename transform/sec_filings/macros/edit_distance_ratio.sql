{% macro edit_distance_ratio(a, b) -%}
  -- Character-level similarity: 1 - (Levenshtein distance / longer length), in [0, 1].
  -- Catches intra-word typos (e.g. "advisrs" vs "advisors") that token-set
  -- similarity cannot see, since Jaccard treats a misspelled token as a wholly
  -- different token. Pair with token_set_similarity via GREATEST() so each metric
  -- covers the other's blind spot (typos vs. word-order / extra words).
  -- Inputs should already be normalized (lower-cased, punctuation-stripped).
  coalesce(
    safe_divide(
      greatest(length({{ a }}), length({{ b }})) - edit_distance({{ a }}, {{ b }}),
      greatest(length({{ a }}), length({{ b }}))
    ),
    0
  )
{%- endmacro %}
