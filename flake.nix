{
  description = "cloud-custodian flake using uv2nix";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.uv2nix.follows = "uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      uv2nix,
      pyproject-nix,
      pyproject-build-systems,
      ...
    }:
    let
      inherit (nixpkgs) lib;

      # Load a uv workspace from a workspace root.
      # Uv2nix treats all uv projects as workspace projects.
      workspace = uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ./.; };

      # Create package overlay from workspace.
      overlay = workspace.mkPyprojectOverlay {
        # Prefer prebuilt binary wheels as a package source.
        sourcePreference = "wheel"; 
      };

      # Create a filtering overlay to remove c7n-awscc
      filterAwsccOverlay = final: prev: 
        let
          # Remove c7n-awscc from the set of packages
          filteredPkgs = lib.filterAttrs (name: value: name != "c7n-awscc") prev;
        in
          filteredPkgs;

      # Extend generated overlay with build fixups
      pyprojectOverrides = final: prev:
        let
          # Helper function to add setuptools to a package's build dependencies
          addSetuptools = pkgName: prev.${pkgName}.overrideAttrs (old: {
            nativeBuildInputs = (old.nativeBuildInputs or []) ++ [
              final.setuptools
            ];
          });
          
          packagesNeedingSetuptools = [
            "crcmod"
            "cos-python-sdk-v5"
            "netifaces"
            "placebo"
          ];
          
          setupToolsOverrides = builtins.listToAttrs (
            map (name: { inherit name; value = addSetuptools name; }) 
            packagesNeedingSetuptools
          );
        in
          setupToolsOverrides;

      pkgs = nixpkgs.legacyPackages.x86_64-linux;

      python = pkgs.python312;

      pythonSet =
        (pkgs.callPackage pyproject-nix.build.packages {
          inherit python;
        }).overrideScope
          (
            lib.composeManyExtensions [
              pyproject-build-systems.overlays.default
              overlay
              filterAwsccOverlay  # Apply our filter for c7n-awscc
              pyprojectOverrides
            ]
          );

      # ====== DEVELOPMENT ENVIRONMENT (EDITABLE) ======
      editableOverlay = workspace.mkEditablePyprojectOverlay {
        root = "$REPO_ROOT";
        members = [ "c7n" ];
      };

      editablePythonSet = pythonSet.overrideScope (
        lib.composeManyExtensions [
          editableOverlay

          (final: prev: {
            c7n = prev.c7n.overrideAttrs (old: {
              src = lib.fileset.toSource {
                root = old.src;
                fileset = lib.fileset.unions [
                  (old.src + "/pyproject.toml")
                  (old.src + "/README.md")
                  (old.src + "/c7n/__init__.py")
                ];
              };

              nativeBuildInputs =
                old.nativeBuildInputs
                ++ final.resolveBuildSystem {
                  editables = [ ];
                };
            });
          })
        ]
      );

      # For editable development environment
      virtualenv = editablePythonSet.mkVirtualEnv "c7n-dev-env" (
        lib.filterAttrs (name: value: name != "c7n-awscc") workspace.deps.all
      );
      
      appEnv = pythonSet.mkVirtualEnv "c7n-app-env" (
        lib.filterAttrs (name: value: name != "c7n-awscc") workspace.deps.default
      );
      
      # Create a wrapper script that uses the appEnv environment
      appScript = pkgs.writeShellScriptBin "custodian" ''
        exec ${appEnv}/bin/custodian "$@"
      '';

    in
    {
      # Use the wrapper script for the default package
      packages.x86_64-linux.default = appScript;

      # Make custodian runnable with `nix run`
      apps.x86_64-linux = {
        default = {
          type = "app";
          program = "${appScript}/bin/custodian";
        };
      };

      # Development shells
      devShells.x86_64-linux = {
        # Impure development environment
        impure = pkgs.mkShell {
          packages = [
            python
            pkgs.uv
          ];
          env =
            {
              # Prevent uv from managing Python downloads
              UV_PYTHON_DOWNLOADS = "never";
              # Force uv to use nixpkgs Python interpreter
              UV_PYTHON = python.interpreter;
            }
            // lib.optionalAttrs pkgs.stdenv.isLinux {
              # Python libraries often load native shared objects using dlopen(3).
              LD_LIBRARY_PATH = lib.makeLibraryPath pkgs.pythonManylinuxPackages.manylinux1;
            };
          shellHook = ''
            unset PYTHONPATH
          '';
        };

        uv2nix = pkgs.mkShell {
          packages = [
            virtualenv
            pkgs.uv
          ];

          env = {
            UV_NO_SYNC = "1";

            # Force uv to use Python interpreter from venv
            UV_PYTHON = "${virtualenv}/bin/python";

            # Prevent uv from downloading managed Python's
            UV_PYTHON_DOWNLOADS = "never";
          };

          shellHook = ''
            # Undo dependency propagation by nixpkgs.
            unset PYTHONPATH
            echo "Welcome to uv2nix dev shell!"
          '';
        };
      };
    };
}
