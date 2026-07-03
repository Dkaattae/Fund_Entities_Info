{% test unique_combination(model, combination_of_columns) %}
-- Grain test: fails if any combination of the given columns appears more
-- than once. Lightweight stand-in for dbt_utils.unique_combination_of_columns
-- (avoids taking on the package dependency). NULLs group together, so rows
-- with NULL key parts are still checked against each other.
select
    {{ combination_of_columns | join(', ') }},
    count(*) as n_rows
from {{ model }}
group by {{ combination_of_columns | join(', ') }}
having count(*) > 1
{% endtest %}
