

def test_every_vmd_command_is_listed_in_exactly_one_stage():
    from vmd_agent import vmd_cli
    listed = [n for _, names in vmd_cli.STAGES for n in names]
    assert sorted(listed) == sorted(vmd_cli.VMD_TOOLS)
