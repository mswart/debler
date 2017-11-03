# Explaination for database opts

## Pkger indepentend pkg options

* `rundeps`: list of runtime-dependencies
* `builddeps`: list of build dependencies

## Rubygems specific pkg options

* `skip_exts`: do not build this specific extension - e.g. it might only be needed on windows
* `so_subdir`: 
* `extra_dirs`: additional directories (or files) that should be installed. path should be relative to gem directory
* `ext_args`: 
