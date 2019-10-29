{{key}} resources
{{underline(provider_name + '.' + key + ' resources', '#')}}

.. toctree::
   :maxdepth: 1
   :titlesonly:

{% for rf in resource_files %}
   {{rf}}
{% endfor %}
