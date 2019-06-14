

{{resource_name}}
{{underline(resource_name)}}

{% if resource.__doc__ %}
{{resource.__doc__}}
{% endif %}


Filters
-------

{% for f in filters %}

{{f.type}}
{{underline(f.type, '+')}}

{{f.__doc__}}

.. c7n-schema:: {{provider_name}}.{{resource_name}}.filters.{{f.type}}

{% endfor %}


Actions
-------

{% for a in actions %}

{{a.type}}
{{underline(a.type, '+')}}

.. c7n-schema:: {{provider_name}}.{{resource_name}}.actions.{{a.type}}

{{a.__doc__}}

{% endfor %}

