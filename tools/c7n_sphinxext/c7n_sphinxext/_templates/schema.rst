
.. container:: toggle

  {# `raw:: html` is used because `.. container` doesn't support empty content #}

  .. raw:: html
     
    <div class="header docutils container" style=""></div>

  .. code-block:: yaml

    {{ schema_yaml|indent(4) }}
