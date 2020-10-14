"""
FAIR adapter
"""
import fair
import fair.version_two.emissions_driven as emissions_driven
import numpy as np
import pandas as pd

from scmdata import ScmRun
from tqdm.autonotebook import tqdm

from ..base import _Adapter
from ._run_fair import run_fair

from __future__ import division

import datetime as dt

import os
import numpy as np
import pandas as pd
from scipy.interpolate import interp1d

from ..constants import molwt

try:
    from scmdata import ScmDataFrame, ScmRun
    has_scmdata = True
except ImportError:
    has_scmdata = False

class SSP245WorldEmms:
    def __init__(self):
        self._loaded = False
        self._loaded_fair_history = False

    @property
    def values(self):
        if not self._loaded:
            self._values = (
                ScmRun(
                    os.path.join(
                        os.path.dirname(__file__),
                        '../SSPs/data/rcmip-emissions-annual-means-4-0-0-ssp-only.csv'),
                        lowercase_cols=True
                )
                .filter(scenario="ssp245", region="World", variable="Emissions*")
            )
            self._values = self._values.interpolate([dt.datetime(y, 1, 1) for y in self._values["year"]])

        self._loaded = True

        return self._values

    @property
    def values_fair_units(self):
        if not self._loaded_fair_history:
            ssp_df_hist = self.values
            for variable in ssp_df_hist.get_unique_meta("variable"):
                in_unit = ssp_df_hist.filter(variable=variable).get_unique_meta("unit", no_duplicates=True)

                try:
                    _, fair_unit, context = _get_fair_col_unit_context(variable)
                except AssertionError:
                    # FaIR does not model the variable
                    assert variable in [
                        'Emissions|F-Gases|HFC|HFC152a',
                        'Emissions|F-Gases|HFC|HFC236fa',
                        'Emissions|F-Gases|HFC|HFC365mfc',
                        'Emissions|F-Gases|NF3',
                        'Emissions|F-Gases|PFC|C3F8',
                        'Emissions|F-Gases|PFC|C4F10',
                        'Emissions|F-Gases|PFC|C5F12',
                        'Emissions|F-Gases|PFC|C7F16',
                        'Emissions|F-Gases|PFC|C8F18',
                        'Emissions|F-Gases|PFC|cC4F8',
                        'Emissions|F-Gases|SO2F2',
                        'Emissions|Montreal Gases|CH2Cl2',
                        'Emissions|Montreal Gases|CHCl3',
                    ]

                    continue

                if in_unit != fair_unit:
                    ssp_df_hist = ssp_df_hist.convert_unit(fair_unit, variable=variable, context=context)

            self._values_fair_history = ssp_df_hist

        self._loaded_fair_history = True

        return self._values_fair_history



# TODO: lazy load this and only load once
ssp245_world_emms_holder = SSP245WorldEmms()


EMISSIONS_SPECIES_UNITS_CONTEXT = pd.DataFrame((
        ('|CO2|MAGICC Fossil and Industrial', 'GtC / yr', None),
        ('|CO2|MAGICC AFOLU', 'GtC / yr', None),
        ('|CH4', 'MtCH4 / yr', None),
        ('|N2O', 'MtN / yr', None),
        ('|Sulfur', 'MtS / yr', None),
        ('|CO', 'MtCO / yr', None),
        ('|VOC', 'MtNMVOC / yr', None),
        ('|NOx', 'MtN / yr', "NOx_conversions"),
        ('|BC', 'MtBC / yr', None),
        ('|OC', 'MtOC / yr', None),
        ('|NH3', 'MtN / yr', None),
        ('|CF4', 'ktCF4 / yr', None),
        ('|C2F6', 'ktC2F6 / yr', None),
        ('|C6F14', 'ktC6F14 / yr', None),
        ('|HFC23', 'ktHFC23 / yr', None),
        ('|HFC32', 'ktHFC32 / yr', None),
        ('|HFC4310mee', 'ktHFC4310mee / yr', None),
        ('|HFC125', 'ktHFC125 / yr', None),
        ('|HFC134a', 'ktHFC134a / yr', None),
        ('|HFC143a', 'ktHFC143a / yr', None),
        ('|HFC227ea', 'ktHFC227ea / yr', None),
        ('|HFC245fa', 'ktHFC245fa / yr', None),
        ('|SF6', 'ktSF6 / yr', None),
        ('|CFC11', 'ktCFC11 / yr', None),
        ('|CFC12', 'ktCFC12 / yr', None),
        ('|CFC113', 'ktCFC113 / yr', None),
        ('|CFC114', 'ktCFC114 / yr', None),
        ('|CFC115', 'ktCFC115 / yr', None),
        ('|CCl4', 'ktCCl4 / yr', None),
        ('|CH3CCl3', 'ktCH3CCl3 / yr', None),
        ('|HCFC22', 'ktHCFC22 / yr', None),
        ('|HCFC141b', 'ktHCFC141b / yr', None),
        ('|HCFC142b', 'ktHCFC142b / yr', None),
        ('|Halon1211', 'ktHalon1211 / yr', None),
        ('|Halon1202', 'ktHalon1202 / yr', None),
        ('|Halon1301', 'ktHalon1301 / yr', None),
        ('|Halon2402', 'ktHalon2402 / yr', None),
        ('|CH3Br', 'ktCH3Br / yr', None),
        ('|CH3Cl', 'ktCH3Cl / yr', None),
    ),
    columns=["species", "in_unit", "context"],
)

def _get_fair_col_unit_context(variable):
    row = EMISSIONS_SPECIES_UNITS_CONTEXT["species"].apply(lambda x: variable.endswith(x))

    in_unit = EMISSIONS_SPECIES_UNITS_CONTEXT[row]["in_unit"]

    assert in_unit.shape[0] == 1, in_unit

    fair_col = int(row[row].index.values) + 1  # first col is time
    in_unit = in_unit.iloc[0]
    context = EMISSIONS_SPECIES_UNITS_CONTEXT[row]["context"].iloc[0]

    return fair_col, in_unit, context


def _scmdf_to_emissions_df(scmdf, include_cfcs=True, startyear=1765, endyear=2100):
    """
    Opens an ScmDataFrame and extracts the data. Interpolates linearly
    between non-consecutive years in the SCEN file. Fills in chlorinated gases
    from a specified SSP scenario.
    Note this is a temporary fix for FaIR 2.0.
    Inputs:
        scmdf: ScmDataFrame
    Keywords:
        include_cfcs: bool
            MAGICC files do not come loaded with CFCs (indices 24-39).
            - if True, use the values from RCMIP for SSPs (all scenarios are
                the same).
            - Use False to ignore and create a 23-species emission file.
        startyear: First year of output file.
        endyear: Last year of output file.
    Returns:
        DataFrame (nt x 39 with year index) of Emissions in the correct format for use with FaIR 2.0 (nt x 23 if ``include_cfcs`` is ``False``)
    """

    # We expect that aeneris and silicone are going to give us a nicely
    # formatted ScmDataFrame with all 23 species present and correct at
    # timesteps 2015, 2020 and ten-yearly to 2100.
    # We also implicitly assume that data up until 2014 will follow SSP
    # historical.
    # This adapter will not be tested on anything else!

    n_cols = 40
    nt = endyear - startyear + 1

    data_out = np.ones((nt, n_cols)) * np.nan
    data_out[:,0] = np.arange(startyear, endyear+1)

    if not has_scmdata:
        raise ImportError("This is not going to work without having scmdata installed")

    if not isinstance(scmdf, ScmDataFrame):
        raise TypeError("scmdf must be an scmdata.ScmDataFrame instance")

    if not include_cfcs:
        raise NotImplementedError("include_cfcs equal to False")

    if scmdf[["model", "scenario"]].drop_duplicates().shape[0] != 1:
        raise AssertionError("Should only have one model-scenario pair")

    scen_start_year = 2015

    scmdf = ScmRun(scmdf.timeseries()).interpolate(
        [dt.datetime(y, 1, 1) for y in range(scen_start_year, endyear + 1)]
    )

    years = scmdf["year"].values
    first_scenyear = years[0]
    first_scen_row = int(first_scenyear-startyear)

    # if correct units and interpolation were guaranteed we could do this for scenario too which is quicker
    hist_df = ssp245_world_emms_holder.values_fair_units.filter(
        year=range(startyear, 2015)
    ).timeseries()

    future_ssp245_df = ssp245_world_emms_holder.values_fair_units.filter(
        year=range(2015, endyear + 1)
    ).timeseries()

    for species in EMISSIONS_SPECIES_UNITS_CONTEXT["species"]:
        fair_col, _, _ = _get_fair_col_unit_context(species)

        hist_df_row = hist_df.index.get_level_values("variable").str.endswith(species)

        data_out[: first_scen_row, fair_col] = hist_df[hist_df_row].values.squeeze()

        future_ssp245_df_row = future_ssp245_df.index.get_level_values("variable").str.endswith(species)

        data_out[first_scen_row :, fair_col] = future_ssp245_df[future_ssp245_df_row].values.squeeze()


    for var_df in scmdf.groupby("variable"):
        variable = var_df.get_unique_meta("variable", no_duplicates=True)
        in_unit = var_df.get_unique_meta("unit", no_duplicates=True)
        fair_col, fair_unit, context = _get_fair_col_unit_context(variable)

        if in_unit != fair_unit:
            var_df_fair_unit = var_df.convert_unit(fair_unit, context=context)
        else:
            var_df_fair_unit = var_df

        data_out[first_scen_row :, fair_col] = var_df_fair_unit.values.squeeze()

    df_out = pd.DataFrame(  index = data_out[:,0],\
                            columns = EMISSIONS_SPECIES_UNITS_CONTEXT["species"],\
                            data = data_out[:,1:])

    return df_out

class FAIR2(_Adapter):
    """
    Adapter for running FAIR
    """

    def _init_model(self, *args, **kwargs):
        pass

    def _run(self, scenarios, cfgs, output_variables, output_config):
        if output_config is not None:
            raise NotImplementedError("`output_config` not implemented for FaIR")

        fair_df = ScmRun(scenarios.timeseries())
        full_cfgs = self._make_full_cfgs(fair_df, cfgs)

        res = run_fair(full_cfgs, output_variables)
        res["climate_model"] = "FaIRv{}".format(self.get_version())

        return res

    def _make_full_cfgs(self, scenarios, cfgs):  # pylint: disable=R0201
        full_cfgs = []
        run_id_block = 0

        for (scenario, model), smdf in tqdm(
            scenarios.timeseries().groupby(["scenario", "model"]),
            desc="Creating FaIR emissions inputs",
        ):
            smdf_in = ScmRun(smdf)
            emissions_df = _scmdf_to_emissions_df(smdf_in)

            #These should pick up values from parameter sets for FaIR
            NotImplementedError
            gas_params_df = pd.DataFrame()
            thermal_params_df = pd.DataFrame()
            ext_forcing_df = pd.DataFrame()



            scenario_cfg = [
                {
                    "scenario": scenario,
                    "model": model,
                    "run_id": run_id_block + i,
                    "inp_df": emissions_df,
                    "cfg" : {"gas_params" : gas_params_df, "thermal_params" : thermal_params_df, "ext_forcing" : ext_forcing_df},\
                    **cfg,
                }
                for i, cfg in enumerate(cfgs)
            ]
            run_id_block += len(scenario_cfg)

            full_cfgs += scenario_cfg

        return full_cfgs
    
    @staticmethod
    def get_version():
        """
        Get the FAIR version being used by this adapter
        Returns
        -------
        str
            The FAIR version id
        """
        return fair.__version__
