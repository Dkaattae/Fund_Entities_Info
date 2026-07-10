{% macro bd_file_number_format() %}
{#- Well-formed SEC broker-dealer file number: prefix up to 3 digits, serial
    up to 5. The bounds matter: LPAD TRUNCATES over-long input, so an
    unbounded pattern would fold a typo like '8-692444' (6-digit serial)
    into the real firm '8-69244' and falsely validate it. -#}
r'^[0-9]{1,3}-[0-9]{1,5}$'
{% endmacro %}

{% macro bd_file_key(col) %}
{#- Reported '8-1447' -> '00801447', the zero-padded form used by
    broker_dealer film_number (prefix LPAD 3 + serial LPAD 5). Only apply to
    values matching bd_file_number_format(). -#}
    concat(
        lpad(split({{ col }}, '-')[offset(0)], 3, '0'),
        lpad(split({{ col }}, '-')[offset(1)], 5, '0')
    )
{% endmacro %}
