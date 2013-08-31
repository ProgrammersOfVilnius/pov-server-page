from update_server_page import Builder


def test_Builder_from_config_all_defaults():
    cp = Builder.ConfigParser()
    Builder.from_config(cp) # should not raise
