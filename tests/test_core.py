import unittest

from http_range import (
    ByteRange,
    ContentRange,
    RangeError,
    parse_content_range,
    parse_range,
)


class ParseRangeTests(unittest.TestCase):
    def test_single_closed_range(self):
        self.assertEqual(parse_range("bytes=0-499", 1000), [ByteRange(0, 499)])

    def test_multiple_ranges(self):
        self.assertEqual(
            parse_range("bytes=0-0,500-999", 1000),
            [ByteRange(0, 0), ByteRange(500, 999)],
        )

    def test_open_ended_range_is_clamped_to_length(self):
        self.assertEqual(parse_range("bytes=500-", 1000), [ByteRange(500, 999)])

    def test_closed_range_end_is_clamped_to_length(self):
        self.assertEqual(parse_range("bytes=0-100000", 1000), [ByteRange(0, 999)])

    def test_suffix_range(self):
        self.assertEqual(parse_range("bytes=-200", 1000), [ByteRange(800, 999)])

    def test_suffix_longer_than_representation_returns_whole_representation(self):
        self.assertEqual(parse_range("bytes=-2000", 1000), [ByteRange(0, 999)])

    def test_unit_is_case_insensitive(self):
        self.assertEqual(parse_range("BYTES=0-9", 100), [ByteRange(0, 9)])

    def test_whitespace_around_intervals_is_ignored(self):
        self.assertEqual(
            parse_range("bytes= 0-9 , 20-29 ", 100),
            [ByteRange(0, 9), ByteRange(20, 29)],
        )

    def test_suffix_range_without_length_is_rejected(self):
        with self.assertRaises(RangeError):
            parse_range("bytes=-10")

    def test_open_ended_range_without_length_is_rejected(self):
        with self.assertRaises(RangeError):
            parse_range("bytes=10-")

    def test_unsupported_unit_is_rejected(self):
        with self.assertRaises(RangeError):
            parse_range("items=0-9", 100)

    def test_missing_equals_is_rejected(self):
        with self.assertRaises(RangeError):
            parse_range("bytes 0-9", 100)

    def test_empty_interval_is_rejected(self):
        with self.assertRaises(RangeError):
            parse_range("bytes=0-9,,20-29", 100)

    def test_reversed_interval_is_rejected(self):
        with self.assertRaises(RangeError):
            parse_range("bytes=10-5", 100)

    def test_interval_without_dash_is_rejected(self):
        with self.assertRaises(RangeError):
            parse_range("bytes=10", 100)

    def test_start_beyond_length_is_rejected(self):
        with self.assertRaises(RangeError):
            parse_range("bytes=100-200", 100)

    def test_suffix_zero_is_rejected(self):
        with self.assertRaises(RangeError):
            parse_range("bytes=-0", 100)

    def test_non_string_value_is_rejected(self):
        with self.assertRaises(RangeError):
            parse_range(123, 100)

    def test_negative_length_is_rejected(self):
        with self.assertRaises(RangeError):
            parse_range("bytes=0-9", -1)


class ByteRangeTests(unittest.TestCase):
    def test_length_is_inclusive(self):
        self.assertEqual(ByteRange(0, 0).length, 1)
        self.assertEqual(ByteRange(0, 499).length, 500)

    def test_negative_start_is_rejected(self):
        with self.assertRaises(RangeError):
            ByteRange(-1, 5)

    def test_reversed_interval_is_rejected(self):
        with self.assertRaises(RangeError):
            ByteRange(5, 4)


class ParseContentRangeTests(unittest.TestCase):
    def test_known_total(self):
        self.assertEqual(
            parse_content_range("bytes 0-499/1000"),
            ContentRange(0, 499, 1000),
        )

    def test_unknown_total(self):
        self.assertEqual(
            parse_content_range("bytes 0-499/*"),
            ContentRange(0, 499, None),
        )

    def test_unknown_total_with_supplied_length(self):
        self.assertEqual(
            parse_content_range("bytes 0-499/*", 1000),
            ContentRange(0, 499, 1000),
        )

    def test_unsatisfied_range(self):
        self.assertEqual(
            parse_content_range("bytes */1000"),
            ContentRange(None, None, 1000),
        )

    def test_legacy_star_unit(self):
        self.assertEqual(
            parse_content_range("*/*"),
            ContentRange(None, None, None),
        )

    def test_total_disagreement_is_rejected(self):
        with self.assertRaises(RangeError):
            parse_content_range("bytes 0-499/1000", 999)

    def test_end_beyond_total_is_rejected(self):
        with self.assertRaises(RangeError):
            parse_content_range("bytes 0-1000/1000")

    def test_reversed_interval_is_rejected(self):
        with self.assertRaises(RangeError):
            parse_content_range("bytes 500-0/1000")

    def test_missing_slash_is_rejected(self):
        with self.assertRaises(RangeError):
            parse_content_range("bytes 0-499")

    def test_unsatisfied_without_total_is_rejected(self):
        with self.assertRaises(RangeError):
            parse_content_range("bytes */*")

    def test_non_string_value_is_rejected(self):
        with self.assertRaises(RangeError):
            parse_content_range(None)

    def test_satisfied_property(self):
        self.assertTrue(parse_content_range("bytes 0-499/1000").satisfied)
        self.assertFalse(parse_content_range("bytes */1000").satisfied)


if __name__ == "__main__":
    unittest.main()
