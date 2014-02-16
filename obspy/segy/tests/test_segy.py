# -*- coding: utf-8 -*-
"""
The obspy.segy test suite.
"""
from __future__ import division
from __future__ import unicode_literals
from future import standard_library  # NOQA
from future.builtins import range
from future.builtins import open

from obspy.core import compatibility
from obspy.core.util import NamedTemporaryFile
from obspy.segy.header import DATA_SAMPLE_FORMAT_PACK_FUNCTIONS, \
    DATA_SAMPLE_FORMAT_UNPACK_FUNCTIONS
from obspy.segy.segy import SEGYBinaryFileHeader, SEGYTraceHeader, SEGYFile, \
    readSEGY
from obspy.segy.tests.header import FILES, DTYPES
import numpy as np
import os
import unittest


class SEGYTestCase(unittest.TestCase):
    """
    Test cases for SEG Y reading and writing..
    """
    def setUp(self):
        # directory where the test files are located
        self.dir = os.path.dirname(__file__)
        self.path = os.path.join(self.dir, 'data')
        # All the files and information about them. These files will be used in
        # most tests. data_sample_enc is the encoding of the data value and
        # sample_size the size in bytes of these samples.
        self.files = FILES
        self.dtypes = DTYPES

    def test_unpackSEGYData(self):
        """
        Tests the unpacking of various SEG Y files.
        """
        for file, attribs in self.files.items():
            data_format = attribs['data_sample_enc']
            endian = attribs['endian']
            count = attribs['sample_count']
            file = os.path.join(self.path, file)
            # Use the with statement to make sure the file closes.
            with open(file, 'rb') as f:
                # Jump to the beginning of the data.
                f.seek(3840)
                # Unpack the data.
                data = DATA_SAMPLE_FORMAT_UNPACK_FUNCTIONS[data_format](
                    f, count, endian)
            # Check the dtype of the data.
            self.assertEqual(data.dtype, self.dtypes[data_format])
            # Proven data values, read with Madagascar.
            correct_data = np.load(file + '.npy').ravel()
            # Compare both.
            np.testing.assert_array_equal(correct_data, data)

    def test_packSEGYData(self):
        """
        Tests the packing of various SEG Y files.
        """
        # Loop over all files.
        for file, attribs in self.files.items():
            # Get some attributes.
            data_format = attribs['data_sample_enc']
            endian = attribs['endian']
            count = attribs['sample_count']
            size = attribs['sample_size']
            non_normalized_samples = attribs['non_normalized_samples']
            dtype = self.dtypes[data_format]
            file = os.path.join(self.path, file)
            # Load the data. This data has previously been unpacked by
            # Madagascar.
            data = np.load(file + '.npy').ravel()
            data = np.require(data, dtype)
            # Load the packed data.
            with open(file, 'rb') as f:
                # Jump to the beginning of the data.
                f.seek(3200 + 400 + 240)
                packed_data = f.read(count * size)
            # The pack functions all write to file objects.
            f = compatibility.BytesIO()
            # Pack the data.
            DATA_SAMPLE_FORMAT_PACK_FUNCTIONS[data_format](f, data, endian)
            # Read again.0.
            f.seek(0, 0)
            new_packed_data = f.read()
            # Check the length.
            self.assertEqual(len(packed_data), len(new_packed_data))
            if len(non_normalized_samples) == 0:
                # The packed data should be totally identical.
                self.assertEqual(packed_data, new_packed_data)
            else:
                # Some test files contain non normalized IBM floating point
                # data. These cannot be reproduced exactly.
                # Just a sanity check to be sure it is only IBM floating point
                # data that does not work completely.
                self.assertEqual(data_format, 1)

                # Read the data as uint8 to be able to directly access the
                # different bytes.
                # Original data.
                packed_data = np.fromstring(packed_data, 'uint8')
                # Newly written.
                new_packed_data = np.fromstring(new_packed_data, 'uint8')

                # Figure out the non normalized fractions in the original data
                # because these cannot be compared directly.
                # Get the position of the first byte of the fraction depending
                # on the endianness.
                if endian == '>':
                    start = 1
                else:
                    start = 2
                # The first byte of the fraction.
                first_fraction_byte_old = packed_data[start::4]
                # First get all zeros in the original data because zeros have
                # to be treated differently.
                zeros = np.where(data == 0)[0]
                # Create a copy and set the zeros to a high number to be able
                # to find all non normalized numbers.
                fraction_copy = first_fraction_byte_old.copy()
                fraction_copy[zeros] = 255
                # Normalized numbers will have no zeros in the first 4 bit of
                # the fraction. This means that the most significant byte of
                # the fraction has to be at least 16 for it to be normalized.
                non_normalized = np.where(fraction_copy < 16)[0]

                # Sanity check if the file data and the calculated data are the
                # same.
                np.testing.assert_array_equal(non_normalized,
                                              np.array(non_normalized_samples))

                # Test all other parts of the packed data. Set dtype to int32
                # to get 4 byte numbers.
                packed_data_copy = packed_data.copy()
                new_packed_data_copy = new_packed_data.copy()
                packed_data_copy.dtype = 'int32'
                new_packed_data_copy.dtype = 'int32'
                # Equalize the non normalized parts.
                packed_data_copy[non_normalized] = \
                    new_packed_data_copy[non_normalized]
                np.testing.assert_array_equal(packed_data_copy,
                                              new_packed_data_copy)

                # Now check the non normalized parts if they are almost the
                # same.
                data = data[non_normalized]
                # Unpack the data again.
                new_packed_data.dtype = 'int32'
                new_packed_data = new_packed_data[non_normalized]
                length = len(new_packed_data)
                f = compatibility.BytesIO()
                f.write(new_packed_data.tostring())
                f.seek(0, 0)
                new_data = DATA_SAMPLE_FORMAT_UNPACK_FUNCTIONS[1](
                    f, length, endian)
                f.close()
                packed_data.dtype = 'int32'
                packed_data = packed_data[non_normalized]
                length = len(packed_data)
                f = compatibility.BytesIO()
                f.write(packed_data.tostring())
                f.seek(0, 0)
                old_data = DATA_SAMPLE_FORMAT_UNPACK_FUNCTIONS[1](
                    f, length, endian)
                f.close()
                # This works because the normalized and the non normalized IBM
                # floating point numbers will be close enough for the internal
                # IEEE representation to be identical.
                np.testing.assert_array_equal(data, new_data)
                np.testing.assert_array_equal(data, old_data)

    def test_packAndUnpackIBMFloat(self):
        """
        Packing and unpacking IBM floating points might yield some inaccuracies
        due to floating point rounding errors.
        This test tests a large number of random floating point numbers.
        """
        # Some random seeds.
        seeds = [1234, 592, 459482, 6901, 0, 7083, 68349]
        endians = ['<', '>']
        # Loop over all combinations.
        for seed in seeds:
            # Generate 50000 random floats from -10000 to +10000.
            np.random.seed(seed)
            data = 200000.0 * np.random.ranf(50000) - 100000.0
            # Convert to float64 in case native floats are different to be
            # able to utilize double precision.
            data = np.require(data, 'float64')
            # Loop over little and big endian.
            for endian in endians:
                # Pack.
                f = compatibility.BytesIO()
                DATA_SAMPLE_FORMAT_PACK_FUNCTIONS[1](f, data, endian)
                # Jump to beginning and read again.
                f.seek(0, 0)
                new_data = DATA_SAMPLE_FORMAT_UNPACK_FUNCTIONS[1](
                    f, len(data), endian)
                f.close()
                # A relative tolerance of 1E-6 is considered good enough.
                rms1 = rms(data, new_data)
                self.assertEqual(True, rms1 < 1E-6)

    def test_packAndUnpackVerySmallIBMFloats(self):
        """
        The same test as test_packAndUnpackIBMFloat just for small numbers
        because they might suffer more from the inaccuracies.
        """
        # Some random seeds.
        seeds = [123, 1592, 4482, 601, 1, 783, 6849]
        endians = ['<', '>']
        # Loop over all combinations.
        for seed in seeds:
            # Generate 50000 random floats from -10000 to +10000.
            np.random.seed(seed)
            data = 1E-5 * np.random.ranf(50000)
            # Convert to float64 in case native floats are different to be
            # able to utilize double precision.
            data = np.require(data, 'float64')
            # Loop over little and big endian.
            for endian in endians:
                # Pack.
                f = compatibility.BytesIO()
                DATA_SAMPLE_FORMAT_PACK_FUNCTIONS[1](f, data, endian)
                # Jump to beginning and read again.
                f.seek(0, 0)
                new_data = DATA_SAMPLE_FORMAT_UNPACK_FUNCTIONS[1](
                    f, len(data), endian)
                f.close()
                # A relative tolerance of 1E-6 is considered good enough.
                rms1 = rms(data, new_data)
                self.assertEqual(True, rms1 < 1E-6)

    def test_packAndUnpackIBMSpecialCases(self):
        """
        Tests the packing and unpacking of several powers of 16 which are
        problematic because they need separate handling in the algorithm.
        """
        endians = ['>', '<']
        # Create the first 10 powers of 16.
        data = []
        for i in range(10):
            data.append(16 ** i)
            data.append(-16 ** i)
        data = np.array(data)
        # Convert to float64 in case native floats are different to be
        # able to utilize double precision.
        data = np.require(data, 'float64')
        # Loop over little and big endian.
        for endian in endians:
            # Pack.
            f = compatibility.BytesIO()
            DATA_SAMPLE_FORMAT_PACK_FUNCTIONS[1](f, data, endian)
            # Jump to beginning and read again.
            f.seek(0, 0)
            new_data = DATA_SAMPLE_FORMAT_UNPACK_FUNCTIONS[1](
                f, len(data), endian)
            f.close()
            # Test both.
            np.testing.assert_array_equal(new_data, data)

    def test_readAndWriteBinaryFileHeader(self):
        """
        Reading and writing should not change the binary file header.
        """
        for file, attribs in self.files.items():
            endian = attribs['endian']
            file = os.path.join(self.path, file)
            # Read the file.
            with open(file, 'rb') as f:
                f.seek(3200)
                org_header = f.read(400)
            header = SEGYBinaryFileHeader(header=org_header, endian=endian)
            # The header writes to a file like object.
            new_header = compatibility.BytesIO()
            header.write(new_header)
            new_header.seek(0, 0)
            new_header = new_header.read()
            # Assert the correct length.
            self.assertEqual(len(new_header), 400)
            # Assert the actual header.
            self.assertEqual(org_header, new_header)

    def test_readAndWriteTextualFileHeader(self):
        """
        Reading and writing should not change the textual file header.
        """
        for file, attribs in self.files.items():
            endian = attribs['endian']
            header_enc = attribs['textual_header_enc']
            file = os.path.join(self.path, file)
            # Read the file.
            with open(file, 'rb') as f:
                org_header = f.read(3200)
                f.seek(0, 0)
                # Initialize an empty SEGY object and set certain attributes.
                segy = SEGYFile()
                segy.endian = endian
                segy.file = f
                segy.textual_header_encoding = None
                # Read the textual header.
                segy._readTextualHeader()
                # Assert the encoding and compare with known values.
                self.assertEqual(segy.textual_header_encoding, header_enc)
            # The header writes to a file like object.
            new_header = compatibility.BytesIO()
            segy._writeTextualHeader(new_header)
            new_header.seek(0, 0)
            new_header = new_header.read()
            # Assert the correct length.
            self.assertEqual(len(new_header), 3200)
            # Assert the actual header.
            self.assertEqual(org_header, new_header)

    def test_readAndWriteTraceHeader(self):
        """
        Reading and writing should not change the trace header.
        """
        for file, attribs in self.files.items():
            endian = attribs['endian']
            file = os.path.join(self.path, file)
            # Read the file.
            with open(file, 'rb') as f:
                f.seek(3600)
                org_header = f.read(240)
            header = SEGYTraceHeader(header=org_header, endian=endian)
            # The header writes to a file like object.
            new_header = compatibility.BytesIO()
            header.write(new_header)
            new_header.seek(0, 0)
            new_header = new_header.read()
            # Assert the correct length.
            self.assertEqual(len(new_header), 240)
            # Assert the actual header.
            self.assertEqual(org_header, new_header)

    def test_readAndWriteSEGY(self, headonly=False):
        """
        Reading and writing again should not change a file.
        """
        for file, attribs in self.files.items():
            file = os.path.join(self.path, file)
            non_normalized_samples = attribs['non_normalized_samples']
            # Read the file.
            with open(file, 'rb') as f:
                org_data = f.read()
            segy_file = readSEGY(file, headonly=headonly)
            with NamedTemporaryFile() as tf:
                out_file = tf.name
                segy_file.write(out_file)
                # Read the new file again.
                with open(out_file, 'rb') as f:
                    new_data = f.read()
            # The two files should have the same length.
            self.assertEqual(len(org_data), len(new_data))
            # Replace the not normalized samples. The not normalized
            # samples are already tested in test_packSEGYData and therefore not
            # tested again here.
            if len(non_normalized_samples) != 0:
                # Convert to 4 byte integers. Any 4 byte numbers work.
                org_data = np.fromstring(org_data, 'int32')
                new_data = np.fromstring(new_data, 'int32')
                # Skip the header (4*960 bytes) and replace the non normalized
                # data samples.
                org_data[960:][non_normalized_samples] = \
                    new_data[960:][non_normalized_samples]
                # Create strings again.
                org_data = org_data.tostring()
                new_data = new_data.tostring()
            # Always write the SEGY File revision number!
            #org_data[3500:3502] = new_data[3500:3502]
            # Test the identity without the SEGY revision number
            self.assertEqual(org_data[:3500], new_data[:3500])
            self.assertEqual(org_data[3502:], new_data[3502:])

    def test_readAndWriteSEGY_headonly(self):
        """
        Reading with headonly=True and writing again should not change a file.
        """
        self.test_readAndWriteSEGY(headonly=True)

    def test_unpackBinaryFileHeader(self):
        """
        Compares some values of the binary header with values read with
        SeisView 2 by the DMNG.
        """
        file = os.path.join(self.path, '1.sgy_first_trace')
        segy = readSEGY(file)
        header = segy.binary_file_header
        # Compare the values.
        self.assertEqual(header.job_identification_number, 0)
        self.assertEqual(header.line_number, 0)
        self.assertEqual(header.reel_number, 0)
        self.assertEqual(header.number_of_data_traces_per_ensemble, 24)
        self.assertEqual(header.number_of_auxiliary_traces_per_ensemble, 0)
        self.assertEqual(header.sample_interval_in_microseconds, 250)
        self.assertEqual(
            header.sample_interval_in_microseconds_of_original_field_recording,
            250)
        self.assertEqual(header.number_of_samples_per_data_trace, 8000)
        self.assertEqual(
            header.
            number_of_samples_per_data_trace_for_original_field_recording,
            8000)
        self.assertEqual(header.data_sample_format_code, 2)
        self.assertEqual(header.ensemble_fold, 0)
        self.assertEqual(header.trace_sorting_code, 1)
        self.assertEqual(header.vertical_sum_code, 0)
        self.assertEqual(header.sweep_frequency_at_start, 0)
        self.assertEqual(header.sweep_frequency_at_end, 0)
        self.assertEqual(header.sweep_length, 0)
        self.assertEqual(header.sweep_type_code, 0)
        self.assertEqual(header.trace_number_of_sweep_channel, 0)
        self.assertEqual(header.sweep_trace_taper_length_in_ms_at_start, 0)
        self.assertEqual(header.sweep_trace_taper_length_in_ms_at_end, 0)
        self.assertEqual(header.taper_type, 0)
        self.assertEqual(header.correlated_data_traces, 0)
        self.assertEqual(header.binary_gain_recovered, 0)
        self.assertEqual(header.amplitude_recovery_method, 0)
        self.assertEqual(header.measurement_system, 0)
        self.assertEqual(header.impulse_signal_polarity, 0)
        self.assertEqual(header.vibratory_polarity_code, 0)
        self.assertEqual(
            header.number_of_3200_byte_ext_file_header_records_following,
            0)

    def test_unpackTraceHeader(self):
        """
        Compares some values of the first trace header with values read with
        SeisView 2 by the DMNG.
        """
        file = os.path.join(self.path, '1.sgy_first_trace')
        segy = readSEGY(file)
        header = segy.traces[0].header
        # Compare the values.
        self.assertEqual(header.trace_sequence_number_within_line, 0)
        self.assertEqual(header.trace_sequence_number_within_segy_file, 0)
        self.assertEqual(header.original_field_record_number, 1)
        self.assertEqual(header.trace_number_within_the_original_field_record,
                         1)
        self.assertEqual(header.energy_source_point_number, 0)
        self.assertEqual(header.ensemble_number, 0)
        self.assertEqual(header.trace_number_within_the_ensemble, 0)
        self.assertEqual(header.trace_identification_code, 1)
        self.assertEqual(
            header.number_of_vertically_summed_traces_yielding_this_trace,
            5)
        self.assertEqual(
            header.number_of_horizontally_stacked_traces_yielding_this_trace,
            0)
        self.assertEqual(header.data_use, 0)
        self.assertEqual(getattr(
            header, 'distance_from_center_of_the_' +
            'source_point_to_the_center_of_the_receiver_group'), 0)
        self.assertEqual(header.receiver_group_elevation, 0)
        self.assertEqual(header.surface_elevation_at_source, 0)
        self.assertEqual(header.source_depth_below_surface, 0)
        self.assertEqual(header.datum_elevation_at_receiver_group, 0)
        self.assertEqual(header.datum_elevation_at_source, 0)
        self.assertEqual(header.water_depth_at_source, 0)
        self.assertEqual(header.water_depth_at_group, 0)
        self.assertEqual(
            header.scalar_to_be_applied_to_all_elevations_and_depths, -100)
        self.assertEqual(header.scalar_to_be_applied_to_all_coordinates, -100)
        self.assertEqual(header.source_coordinate_x, 0)
        self.assertEqual(header.source_coordinate_y, 0)
        self.assertEqual(header.group_coordinate_x, 300)
        self.assertEqual(header.group_coordinate_y, 0)
        self.assertEqual(header.coordinate_units, 0)
        self.assertEqual(header.weathering_velocity, 0)
        self.assertEqual(header.subweathering_velocity, 0)
        self.assertEqual(header.uphole_time_at_source_in_ms, 0)
        self.assertEqual(header.uphole_time_at_group_in_ms, 0)
        self.assertEqual(header.source_static_correction_in_ms, 0)
        self.assertEqual(header.group_static_correction_in_ms, 0)
        self.assertEqual(header.total_static_applied_in_ms, 0)
        self.assertEqual(header.lag_time_A, 0)
        self.assertEqual(header.lag_time_B, 0)
        self.assertEqual(header.delay_recording_time, -100)
        self.assertEqual(header.mute_time_start_time_in_ms, 0)
        self.assertEqual(header.mute_time_end_time_in_ms, 0)
        self.assertEqual(header.number_of_samples_in_this_trace, 8000)
        self.assertEqual(header.sample_interval_in_ms_for_this_trace, 250)
        self.assertEqual(header.gain_type_of_field_instruments, 0)
        self.assertEqual(header.instrument_gain_constant, 24)
        self.assertEqual(header.instrument_early_or_initial_gain, 0)
        self.assertEqual(header.correlated, 0)
        self.assertEqual(header.sweep_frequency_at_start, 0)
        self.assertEqual(header.sweep_frequency_at_end, 0)
        self.assertEqual(header.sweep_length_in_ms, 0)
        self.assertEqual(header.sweep_type, 0)
        self.assertEqual(header.sweep_trace_taper_length_at_start_in_ms, 0)
        self.assertEqual(header.sweep_trace_taper_length_at_end_in_ms, 0)
        self.assertEqual(header.taper_type, 0)
        self.assertEqual(header.alias_filter_frequency, 1666)
        self.assertEqual(header.alias_filter_slope, 0)
        self.assertEqual(header.notch_filter_frequency, 0)
        self.assertEqual(header.notch_filter_slope, 0)
        self.assertEqual(header.low_cut_frequency, 0)
        self.assertEqual(header.high_cut_frequency, 0)
        self.assertEqual(header.low_cut_slope, 0)
        self.assertEqual(header.high_cut_slope, 0)
        self.assertEqual(header.year_data_recorded, 2005)
        self.assertEqual(header.day_of_year, 353)
        self.assertEqual(header.hour_of_day, 15)
        self.assertEqual(header.minute_of_hour, 7)
        self.assertEqual(header.second_of_minute, 54)
        self.assertEqual(header.time_basis_code, 0)
        self.assertEqual(header.trace_weighting_factor, 0)
        self.assertEqual(
            header.geophone_group_number_of_roll_switch_position_one, 2)
        self.assertEqual(header.geophone_group_number_of_trace_number_one, 2)
        self.assertEqual(header.geophone_group_number_of_last_trace, 0)
        self.assertEqual(header.gap_size, 0)
        self.assertEqual(header.over_travel_associated_with_taper, 0)
        self.assertEqual(
            header.x_coordinate_of_ensemble_position_of_this_trace, 0)
        self.assertEqual(
            header.y_coordinate_of_ensemble_position_of_this_trace, 0)
        self.assertEqual(
            header.for_3d_poststack_data_this_field_is_for_in_line_number, 0)
        self.assertEqual(
            header.for_3d_poststack_data_this_field_is_for_cross_line_number,
            0)
        self.assertEqual(header.shotpoint_number, 0)
        self.assertEqual(
            header.scalar_to_be_applied_to_the_shotpoint_number, 0)
        self.assertEqual(header.trace_value_measurement_unit, 0)
        self.assertEqual(header.transduction_constant_mantissa, 0)
        self.assertEqual(header.transduction_constant_exponent, 0)
        self.assertEqual(header.transduction_units, 0)
        self.assertEqual(header.device_trace_identifier, 0)
        self.assertEqual(header.scalar_to_be_applied_to_times, 0)
        self.assertEqual(header.source_type_orientation, 0)
        self.assertEqual(header.source_energy_direction_mantissa, 0)
        self.assertEqual(header.source_energy_direction_exponent, 0)
        self.assertEqual(header.source_measurement_mantissa, 0)
        self.assertEqual(header.source_measurement_exponent, 0)
        self.assertEqual(header.source_measurement_unit, 0)

    def test_readBytesIO(self):
        """
        Tests reading from BytesIO instances.
        """
        # 1
        file = os.path.join(self.path, 'example.y_first_trace')
        with open(file, 'rb') as f:
            data = f.read()
        st = readSEGY(compatibility.BytesIO(data))
        self.assertEqual(len(st.traces[0].data), 500)
        # 2
        file = os.path.join(self.path, 'ld0042_file_00018.sgy_first_trace')
        with open(file, 'rb') as f:
            data = f.read()
        st = readSEGY(compatibility.BytesIO(data))
        self.assertEqual(len(st.traces[0].data), 2050)
        # 3
        file = os.path.join(self.path, '1.sgy_first_trace')
        with open(file, 'rb') as f:
            data = f.read()
        st = readSEGY(compatibility.BytesIO(data))
        self.assertEqual(len(st.traces[0].data), 8000)
        # 4
        file = os.path.join(self.path, '00001034.sgy_first_trace')
        with open(file, 'rb') as f:
            data = f.read()
        st = readSEGY(compatibility.BytesIO(data))
        self.assertEqual(len(st.traces[0].data), 2001)
        # 5
        file = os.path.join(self.path, 'planes.segy_first_trace')
        with open(file, 'rb') as f:
            data = f.read()
        st = readSEGY(compatibility.BytesIO(data))
        self.assertEqual(len(st.traces[0].data), 512)


def rms(x, y):
    """
    Normalized RMS

    Taken from the mtspec library:
    https://github.com/krischer/mtspec
    """
    return np.sqrt(((x - y) ** 2).mean() / (x ** 2).mean())


def suite():
    return unittest.makeSuite(SEGYTestCase, 'test')


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
