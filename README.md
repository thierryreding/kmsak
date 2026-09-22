# Kernel Maintainer's Swiss Army Knife

This is a collection of (hopefully) useful commands for Linux kernel
maintainers.

## Device tree checks

The `dtbs` command provides functionality to validate device trees against
DT schemas.

If you're primarily interested in just validating the tree, run the `check`
subcommand, which will validate each of the device trees and logs the output
to a directory.

A useful set of subcommands are: `snapshot`, `analyze` and `diff`. After an
invocation of `check`, the `snapshot` subcommand can be used to archive the
results in a specified external directory (`base` is usually a good name for
a vanilla tree).

Logs from such an external directory can be parsed by the `analyze` command,
which will show a list of issues found in the logs and count how many of them
are unique, along with the number of instances per unique issue. This can
help focus efforts to eliminate warnings on those that occur most often. A
quick summary of where things are at can be generated with the `todo` command
which lists the DTS files and the number of issues encountered in it.

After picking an issue and resolving it, run `check` and `snapshot` again and
make sure to archive the new logs to a different directory. The `diff` command
can now be used to show how the logs have changed between the two snapshots.
This is useful when trying to determine if indeed all the warnings that were
supposed to be fixed by a change have indeed gone away.
