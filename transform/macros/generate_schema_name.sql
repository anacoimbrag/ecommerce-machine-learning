{# Usa o schema custom do modelo tal como declarado (ex.: "marts"), sem o
   prefixo padrão do dbt "<target_schema>_<custom_schema>". #}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- set default_schema = target.schema -%}
    {%- if custom_schema_name is none -%}
        {{ default_schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
