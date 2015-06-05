# This file is part of Hashdist to setup Hashdist environment for bash.
#
# We provide a 'hit' Bash function, that checks for subcommand is called. If it
# is "load" or "unload", then it hooks them up with Bash to do the right thing.
# Otherwise it just forwards the arguments to the 'hit' program.

function hit {
    _hit_subcommand=$1;

    case $_hit_subcommand in
        "load"|"unload")
            hit_commands="$(command hit "$@" --print-bash-commands)"
            if [ $? -eq 0 ]; then
                # Evaluate the commands that hit supplied using Bash
                eval "$hit_commands"
            else
                # If there was an error in hit, show the error messages
                echo "$hit_commands"
            fi
            ;;
        *)
            command hit "$@"
            ;;
    esac
}
