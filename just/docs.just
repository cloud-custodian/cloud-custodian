set working-directory := ".."

@_default:
    just --list docs

# Build HTML documentation with Sphinx.
@html:
    make -f docs/Makefile.sphinx html

# Clean Sphinx build artefacts.
@clean:
    make -f docs/Makefile.sphinx clean
