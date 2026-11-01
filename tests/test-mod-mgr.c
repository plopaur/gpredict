/*
 * Tests for the module manager.
 *
 * mod-mgr.c is included directly so the tests can reset its internal state
 * between test cases. Its dependencies (sat-cfg, gtk-sat-module, ...) are
 * replaced by the small stubs below, so no configuration files or satellite
 * data are needed.
 */
#include "mod-mgr.c"

GtkWidget      *app = NULL;

/* values returned by the sat-cfg stubs */
static const gchar *cfg_open_modules = NULL;
static gint     cfg_page = 0;

/* values stored by the sat-cfg stubs */
static gchar   *saved_open_modules = NULL;

/* number of times gtk_sat_module_new() was called */
static gint     modules_created = 0;


/* Fake GtkSatModule type with the real instance structure */
G_DEFINE_TYPE(GtkSatModule, gtk_sat_module, GTK_TYPE_BOX)

static void gtk_sat_module_class_init(GtkSatModuleClass * class)
{
    (void)class;
}

static void gtk_sat_module_init(GtkSatModule * module)
{
    (void)module;
}

static GtkWidget *new_module(const gchar * name, gtk_sat_mod_state_t state)
{
    GtkSatModule   *module;

    module = g_object_new(GTK_TYPE_SAT_MODULE, NULL);
    module->name = g_strdup(name);
    module->state = state;

    /* the notebook does not select hidden pages */
    gtk_widget_show(GTK_WIDGET(module));

    return GTK_WIDGET(module);
}

GtkWidget      *gtk_sat_module_new(const gchar * cfgfile)
{
    gchar          *name;
    GtkWidget      *module;

    modules_created++;

    name = g_path_get_basename(cfgfile);
    *g_strrstr(name, ".mod") = '\0';
    module = new_module(name, GTK_SAT_MOD_STATE_DOCKED);
    g_free(name);

    return module;
}

void gtk_sat_module_reload_sats(GtkSatModule * module)
{
    (void)module;
}

gboolean module_window_config_cb(GtkWidget * widget,
                                 GdkEventConfigure * event, gpointer data)
{
    (void)widget;
    (void)event;
    (void)data;

    return FALSE;
}

gchar          *get_modules_dir(void)
{
    return g_strdup("modules");
}

gchar          *logo_file_name(const gchar * logo)
{
    (void)logo;

    return g_strdup("");
}

mod_cfg_status_t mod_cfg_save(gchar * modname, GKeyFile * cfgdata)
{
    (void)modname;
    (void)cfgdata;

    return MOD_CFG_OK;
}

gchar          *sat_cfg_get_str(sat_cfg_str_e param)
{
    (void)param;

    return g_strdup(cfg_open_modules);
}

void sat_cfg_set_str(sat_cfg_str_e param, const gchar * value)
{
    (void)param;

    g_free(saved_open_modules);
    saved_open_modules = g_strdup(value);
}

gint sat_cfg_get_int(sat_cfg_int_e param)
{
    (void)param;

    return cfg_page;
}

void sat_cfg_set_int(sat_cfg_int_e param, gint value)
{
    (void)param;
    (void)value;
}

gboolean sat_cfg_get_bool(sat_cfg_bool_e param)
{
    (void)param;

    return FALSE;
}

void sat_log_log(sat_log_level_t level, const char *fmt, ...)
{
    (void)level;
    (void)fmt;
}


/* Reset the module manager and create a new notebook */
static GtkNotebook *setup(const gchar * openmods, gint page)
{
    g_slist_free(modules);
    modules = NULL;
    cfg_open_modules = openmods;
    cfg_page = page;
    modules_created = 0;

    return GTK_NOTEBOOK(mod_mgr_create());
}

static const gchar *page_name(GtkNotebook * notebook, gint page)
{
    return GTK_SAT_MODULE(gtk_notebook_get_nth_page(notebook, page))->name;
}

static void test_get_module(void)
{
    GtkWidget      *amsat;
    GtkWidget      *iss;

    setup(NULL, 0);
    g_assert_null(mod_mgr_get_module("AMSAT"));

    amsat = new_module("AMSAT", GTK_SAT_MOD_STATE_DOCKED);
    iss = new_module("ISS", GTK_SAT_MOD_STATE_WINDOW);
    mod_mgr_add_module(amsat, TRUE);
    mod_mgr_add_module(iss, FALSE);

    g_assert_true(mod_mgr_get_module("AMSAT") == amsat);
    g_assert_true(mod_mgr_get_module("ISS") == iss);
    g_assert_null(mod_mgr_get_module("NOAA"));
    g_assert_null(mod_mgr_get_module("amsat"));

    mod_mgr_remove_module(amsat);
    g_assert_null(mod_mgr_get_module("AMSAT"));
    g_assert_true(mod_mgr_get_module("ISS") == iss);

    g_object_ref_sink(iss);
    g_object_unref(iss);
}

static void test_create_skips_duplicates(void)
{
    GtkNotebook    *notebook;

    notebook = setup("AMSAT;ISS;AMSAT;ISS;AMSAT", 0);

    g_assert_cmpint(modules_created, ==, 2);
    g_assert_cmpint(g_slist_length(modules), ==, 2);
    g_assert_cmpint(gtk_notebook_get_n_pages(notebook), ==, 2);
    g_assert_cmpstr(page_name(notebook, 0), ==, "AMSAT");
    g_assert_cmpstr(page_name(notebook, 1), ==, "ISS");
}

static void test_create_without_duplicates(void)
{
    GtkNotebook    *notebook;

    notebook = setup("AMSAT;ISS;NOAA", 1);

    g_assert_cmpint(modules_created, ==, 3);
    g_assert_cmpint(gtk_notebook_get_n_pages(notebook), ==, 3);
    g_assert_cmpint(gtk_notebook_get_current_page(notebook), ==, 1);
}

static void test_create_keeps_current_page(void)
{
    GtkNotebook    *notebook;

    /* the duplicate comes before the saved page */
    notebook = setup("AMSAT;AMSAT;ISS", 2);
    g_assert_cmpint(gtk_notebook_get_n_pages(notebook), ==, 2);
    g_assert_cmpstr(page_name(notebook,
                              gtk_notebook_get_current_page(notebook)),
                    ==, "ISS");

    /* the duplicate comes after the saved page */
    notebook = setup("AMSAT;ISS;AMSAT", 1);
    g_assert_cmpint(gtk_notebook_get_n_pages(notebook), ==, 2);
    g_assert_cmpstr(page_name(notebook,
                              gtk_notebook_get_current_page(notebook)),
                    ==, "ISS");

    notebook = setup("AMSAT;ISS;AMSAT", 0);
    g_assert_cmpstr(page_name(notebook,
                              gtk_notebook_get_current_page(notebook)),
                    ==, "AMSAT");
}

static void test_save_state_after_duplicates(void)
{
    setup("AMSAT;ISS;AMSAT", 0);
    mod_mgr_save_state();

    g_assert_cmpstr(saved_open_modules, ==, "AMSAT;ISS");
}

static void test_raise_docked_module(void)
{
    GtkNotebook    *notebook;

    notebook = setup("AMSAT;ISS;NOAA", 2);
    g_assert_cmpint(gtk_notebook_get_current_page(notebook), ==, 2);

    mod_mgr_raise_module(mod_mgr_get_module("AMSAT"));
    g_assert_cmpint(gtk_notebook_get_current_page(notebook), ==, 0);

    mod_mgr_raise_module(mod_mgr_get_module("ISS"));
    g_assert_cmpint(gtk_notebook_get_current_page(notebook), ==, 1);
}

static void test_raise_undocked_module(void)
{
    GtkNotebook    *notebook;
    GtkWidget      *module;
    GtkWidget      *win;

    notebook = setup("AMSAT;ISS", 1);

    module = new_module("NOAA", GTK_SAT_MOD_STATE_WINDOW);
    win = gtk_window_new(GTK_WINDOW_TOPLEVEL);
    GTK_SAT_MODULE(module)->win = win;
    mod_mgr_add_module(module, FALSE);
    gtk_container_add(GTK_CONTAINER(win), module);
    g_assert_false(gtk_widget_get_visible(win));

    mod_mgr_raise_module(mod_mgr_get_module("NOAA"));

    g_assert_true(gtk_widget_get_visible(win));
    g_assert_cmpint(gtk_notebook_get_current_page(notebook), ==, 1);

    mod_mgr_remove_module(module);
    gtk_widget_destroy(win);
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);

    if (!gtk_init_check(&argc, &argv))
    {
        g_printerr("No display available, skipping tests\n");
        return 77;
    }

    app = gtk_window_new(GTK_WINDOW_TOPLEVEL);

    g_test_add_func("/mod-mgr/get-module", test_get_module);
    g_test_add_func("/mod-mgr/create/skips-duplicates",
                    test_create_skips_duplicates);
    g_test_add_func("/mod-mgr/create/without-duplicates",
                    test_create_without_duplicates);
    g_test_add_func("/mod-mgr/create/keeps-current-page",
                    test_create_keeps_current_page);
    g_test_add_func("/mod-mgr/save-state-after-duplicates",
                    test_save_state_after_duplicates);
    g_test_add_func("/mod-mgr/raise/docked", test_raise_docked_module);
    g_test_add_func("/mod-mgr/raise/undocked", test_raise_undocked_module);

    return g_test_run();
}
