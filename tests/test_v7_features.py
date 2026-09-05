from pathlib import Path

from render.export_names import filename_slug, unique_path
from music.groove import clave_offsets_for_measure, normalize_groove
from render.notation import event_segments, events_to_ly_voice


def test_export_filename_uses_song_title_and_uniques(tmp_path):
    assert filename_slug('My Fine Samba!') == 'My_Fine_Samba'
    first = unique_path(tmp_path, 'My_Fine_Samba', '.mp3')
    assert first.name == 'My_Fine_Samba.mp3'
    first.write_text('exists')
    assert unique_path(tmp_path, 'My_Fine_Samba', '.mp3').name == 'My_Fine_Samba-2.mp3'


def test_rhumba_clave_delays_third_three_side_attack():
    assert normalize_groove('rhumba 3-2', 'bossa') == 'rumba_3_2'
    assert clave_offsets_for_measure(0, 'clave_3_2', 'bossa') == [0.0, 1.5, 3.0]
    assert clave_offsets_for_measure(0, 'rumba_3_2', 'bossa') == [0.0, 1.5, 3.5]
    assert clave_offsets_for_measure(1, 'rumba_3_2', 'bossa') == [1.0, 2.5]


def test_notation_event_crossing_barline_is_split():
    segments = event_segments({'pitch': 60, 'start': 3.5, 'duration': 1.0}, total_beats=8.0)
    assert segments == [(3.5, 0.5, 60), (4.0, 0.5, 60)]
    ly = events_to_ly_voice([{'pitch': 60, 'start': 3.5, 'duration': 1.0}], 8.0, 120, 'C')
    # The event is rendered as an eighth note before the barline and an eighth after,
    # with measure-completing rests rather than an overfull 4.5-beat bar.
    assert 'c\'8' in ly or 'c8' in ly
