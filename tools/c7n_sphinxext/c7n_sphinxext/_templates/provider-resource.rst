.. _{{provider_name}}.{{key}}:

{{provider_name}}.{{key}}
{{underline(provider_name + '.' + key, '#')}}

{% for r in resources %}
{{render_resource(provider_name + '.' + r.type)}}
{% endfor %}
