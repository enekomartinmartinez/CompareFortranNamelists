#!/bin/env python3
import uuid
from pathlib import Path
from copy import deepcopy
import json

import f90nml


class Namelist:
    # TODO document
    def __init__(self, namelist_path, label=None):
        self.namelist_path = Path(namelist_path)
        self.namelist = f90nml.read(self.namelist_path)
        self.label = label

    def update(self, namelist, elements="all"):
        # TODO document
        diff = NamelistDiff(self.namelist.todict(), "self")
        diff.diff(namelist, "new", inplace=True)

        # apply changes to namelist
        if elements in ("all", "common") and ("self", "new") in diff.different:
            Namelist._update_nml(
                self.namelist, diff.different[("self", "new")], -1)
        if elements in ("all", "new") and "new" in diff.unique:
            Namelist._update_nml(self.namelist, diff.unique["new"], None)

    def diff(self: 'Namelist', reference: 'Namelist') -> 'NamelistDiff':
        """
        Compute the difference between current Namelist and other.
        """
        # TODO document
        diff = NamelistDiff(self.namelist.todict(), self.label)
        diff.diff(reference.namelist.todict(), reference.label, inplace=True)

        return diff

    def write(self, out=None, patch=False, overwrite=False):
        """
        Write namefile to a file.

        Parameter
        ---------
        out: str or pathlib.Path or None (optional)
            Name of the output file. If not given objects namelist_path
            attribute will be used. Default is None.
        patch: bool (optional)
            If True will writte the file using patch method and original
            file. This keeps the comments in the file. Default is False.
        overwrite: bool (optional)
            If False and output file exists the original file will be
            move with '.bak' extension. If True and any file with the
            same name will be removed. Default is False.

        """
        # make a backup of old namelists
        if out is None:
            out = self.namelist_path
        else:
            out = Path(out)

        if out.exists() and not overwrite:
            path = out.parent
            name = out.name
            cpy = name + ".0.bak"
            for i in range(1001):
                if (path / cpy).exists():
                    cpy = name + f".{i+1}.bak"
                else:
                    break

            if i == 1000:
                raise ValueError(f"Too many copies [{i}]")

            old_file_path = path / cpy
            print(f"copy {out} to {old_file_path}")
            out.rename(old_file_path)
        else:
            old_file_path = self.namelist_path

        # write namelist
        if patch:
            if out == old_file_path:
                tmp_fn = str(uuid.uuid4())
                f90nml.patch(old_file_path, self.namelist, tmp_fn)
                old_file_path.unlink()
                tmp_fn.rename(out)
            else:
                f90nml.patch(old_file_path, self.namelist, out)
        else:
            self.namelist.write(out, force=True)

    @staticmethod
    def _update_nml(nml, changes, element):
        """Update the namelist with the changes dictionary"""
        for key, value in changes.items():
            if isinstance(value, dict):
                if key not in nml:
                    nml[key] = {}
                Namelist._update_nml(nml[key], value, element)
            elif element is None:
                nml[key] = value
            else:
                nml[key] = value[element]


class NamelistDiff():
    # TODO document
    def __init__(self, input, label):
        self.unique = {label: input}
        self.equal = {}
        self.different = {}
        # Labels holder
        self._labels = [label]
        # Other attributes used for the methods
        # Just to avpid passing the each time to the methods
        self._isdiff = None

        if not isinstance(label, str):
            # TODO write error message
            raise TypeError
        if not isinstance(input, dict):
            # TODO write error message
            raise TypeError

    def __str__(self):
        out = "NamelistDiff object\n"
        out += "\nUnique values:\n"
        out += self._dump(self.unique)
        out += "\nEqual values:\n"
        out += self._dump(self.equal)
        out += "\nDifferent values:\n"
        out += self._dump(self.different)
        return out

    def _dump(self, section):
        out = ""
        for key in section:
            out += "  "+" ".join(key) + "\n    "
            out += json.dumps(
                section[key], sort_keys=True, indent=2
            ).replace("\n", "\n    ")
        return out

    def copy(self):
        """Copy the object."""
        return deepcopy(self)

    def diff(self, new_input, new_label, inplace=False):
        """
        Compute the difference of current object with a new namelist.

        Parameters
        ----------
        new_input: str or pathlib.Path or f90nml.namelist.Namelist or dict
            New input data. If str or pathlib.Path it will be read from
            a file. Otherwise, the input object information will be used.
        new_label: str
            Label for the new input data. It is recommended to use a
            "safe" name with no whitespaces or special characters.
        inplace: bool (optional)
            If True it will modify the current object. Otherwise, it will
            return a new object with the method result. Default is False.

        """
        if new_label in self._labels:
            # TODO write error message
            raise ValueError
        if not isinstance(new_label, str):
            # TODO write error message
            raise TypeError
        if isinstance(new_input, (str, Path)):
            new_input = f90nml.read(new_input).todict()
        elif isinstance(new_input, f90nml.namelist.Namelist):
            new_input = new_input.todict()
        elif not isinstance(new_input, dict):
            # TODO write error message
            raise TypeError

        if inplace:
            # Mutates current object
            self._diff(new_input.copy(), new_label)
            return None
        else:
            # Creates a copy for the difference
            new_diff = self.copy()
            new_diff._diff(new_input.copy(), new_label)
            return new_diff

    def _diff(self, input, label):
        """Method for computing the differences"""
        # Compare existing unique dicts
        for key, values in self.unique.items():
            self._isdiff = False
            self._compare_dicts(values, input, [(key, label)])
        # Compare existing equal dicts
        for key, values in self.equal.items():
            self._isdiff = False
            self._compare_dicts(values, input, [(*key, label)])
        # Compare existing different dicts
        for key, values in self.different.items():
            self._isdiff = True
            self._compare_dicts(values, input, [(*key, label)])

        # Writte the value still hold in input (unique)
        if input:
            self.unique[label] = input.copy()

        # Remove those sections that are empty
        for section in ("unique", "equal", "different"):
            sec = getattr(self, section)
            keys = [key for key in sec if not sec[key]]
            for key in keys:
                del sec[key]

        # Reset to None arguments
        self._isdiff = None

    def _compare_dicts(self, self_nml, in_nml, path):
        """
        Compare the keys and values between two dictionaries and update
        a NamelistDiff object
        """
        for key in set(self_nml).intersection(in_nml):
            new_path = path + [key]
            if isinstance(self_nml[key], dict):
                # keep entering a nested level
                self._compare_dicts(self_nml[key], in_nml[key], new_path)
                # Delete groups from previous dictionaries if they are
                # empty after checking their values
                if not self_nml[key]:
                    del self_nml[key]
                if not in_nml[key]:
                    del in_nml[key]
            else:
                # compare values
                self._compare_values(self_nml[key], in_nml[key], new_path)
                # Delete value from previous dictionaries
                del self_nml[key], in_nml[key]

    def _compare_values(self, self_val, ref_val, path):
        """Compare two values from a namelist"""
        if self._isdiff:
            # It is already a different values dictionary, no need to
            # compare the values
            self._update_dict(self.different, path, self_val + [ref_val])
        if self_val == ref_val:
            # Elements are equal
            self._update_dict(self.equal, path, self_val)
        else:
            # First n-1 values are equal and last one different
            self._update_dict(
                self.different, path,
                (len(path[0])-1)*[self_val] + [ref_val]
            )

    def _update_dict(self, section, path, value):
        """Update dictionary addying new entries if needed"""
        cdict = section
        # Iterate over the path in the dictionary
        for key in path[:-1]:
            if key not in cdict:
                # Create key if neccessary
                cdict[key] = {}
            cdict = cdict[key]
        # Assign the new value
        cdict[path[-1]] = value

    def to_spreadsheet(self, out):
        """
        Save the difference information in an spreadsheet file

        Parameters
        ----------
        out: str or pathlib.Path
            Name of the output file to save

        """
        # TODO find a cleaner way to do this import
        # without forcing pandas dependency
        import pandas as pd
        # Create a Pandas Excel writer using XlsxWriter as the engine.
        writer = pd.ExcelWriter(out, engine='xlsxwriter')
        # Write each dataframe to a different worksheet.
        for key in self.unique:
            self._convert_to_df(self.unique[key], ("value",), pd).to_excel(
                writer, sheet_name=f'{key} unique')
        for key in self.equal:
            self._convert_to_df(self.equal[key], ("value",), pd).to_excel(
                writer, sheet_name=f"{'_'.join(key)} equal")
        for key in self.different:
            self._convert_to_df(self.different[key], key, pd).to_excel(
                writer, sheet_name=f"{'_'.join(key)} different")
        # Close the Pandas Excel writer and output the Excel file.
        writer.save()

    @staticmethod
    def _convert_to_df(indict, varcols, pd):
        """Convert a dictionary to a pandas.DataFrame"""
        n_varcols = len(varcols)
        out = NamelistDiff._to_lists(indict, n_varcols)
        # Convert all the list to the same length by prepending Nones
        out_n = max([len(out_i) for out_i in out])
        out = [[None]*(out_n-len(out_i))+out_i for out_i in out]
        # Create pandas DataFrame and moify its columns names
        df = pd.DataFrame(out)
        df.columns = [
            f"level {i}" for i in range(len(df.columns)-n_varcols)
            ] + list(varcols)
        return df

    @staticmethod
    def _to_lists(indict, n_values):
        """Search along dictionary to create each row list"""
        if isinstance(indict, dict):
            # continue searching
            outs = []
            for key, values in indict.items():
                out = NamelistDiff._to_lists(values, n_values)
                outs += [[key] + val for val in out]
            return outs
        elif n_values == 1:
            # unique and equal sections have only one value (create a list)
            return [[indict]]
        else:
            # difference section has more than one value (already a list)
            return [indict]


if __name__ == '__main__':
    pass
