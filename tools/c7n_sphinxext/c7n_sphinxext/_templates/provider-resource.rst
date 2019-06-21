{{provider_name}}.{{key}} resources
{{underline(provider_name + '.' + key + ' resources', '#')}}

{% if resources|length > 1 %}
{% for r in resources %}
  - :ref:`{{ provider_name + '.' + r.type }} <{{ provider_name + '.' + r.type }}>`
{% endfor %}
{% endif %}

{% for r in resources %}
{{render_resource(provider_name + '.' + r.type)}}
{% endfor %}
