#include "tests.h"
#include <gpac/isomedia.h>

/* An in-memory item keeps a copy of its bytes in infe->full_path. On write,
 * DoWriteMeta opens full_path as a file name when data_len is 0, so the copy
 * must be NUL-terminated (#4006: heap-buffer-overflow read in gf_fopen_ex).
 * Under --enable-sanitizer, the unpatched library aborts inside gf_isom_close(). */
unittest(meta_item_memory_zero_length)
{
#if !defined(GPAC_DISABLE_ISOM) && !defined(GPAC_DISABLE_ISOM_WRITE)
	const char *path = "meta-item-memory.mp4";
	/* Exact-size heap buffers with no terminator, as callers pass them. */
	char *payload = gf_malloc(3);
	char *empty = gf_malloc(1);
	GF_ISOFile *file = NULL;
	GF_Err e;
	u32 data_id = 0, empty_id = 0, out_size = 0, out_alloc = 0;
	u8 *out = NULL;

	assert_not_null(payload);
	assert_not_null(empty);
	if (!payload || !empty) goto exit;
	memcpy(payload, "abc", 3);
	empty[0] = 'x';

	/* Edit mode: items stay in memory until gf_isom_close() writes the file. */
	file = gf_isom_open(path, GF_ISOM_WRITE_EDIT, NULL);
	assert_not_null(file);
	if (!file) goto exit;
	e = gf_isom_set_meta_type(file, GF_TRUE, 0, GF_4CC('t', 'e', 's', 't'));
	assert_equal(e, GF_OK, "%d");
	if (e) goto exit;

	/* Valid control: a 3-byte item. */
	e = gf_isom_add_meta_item_memory(file, GF_TRUE, 0, "data", &data_id, GF_4CC('m', 'i', 'm', 'e'),
		"text/plain", NULL, NULL, payload, 3, NULL);
	assert_equal(e, GF_OK, "%d");
	if (e) goto exit;

	/* Trigger: a zero-length item; its full_path is later used as a file name. */
	e = gf_isom_add_meta_item_memory(file, GF_TRUE, 0, "empty", &empty_id, GF_4CC('m', 'i', 'm', 'e'),
		"text/plain", NULL, NULL, empty, 0, NULL);
	assert_equal(e, GF_OK, "%d");
	if (e) goto exit;

	/* Writing reaches DoWriteMeta -> gf_fopen(full_path): over-read without the fix. */
	e = gf_isom_close(file);
	file = NULL;
	assert_equal(e, GF_OK, "%d");
	if (e) goto exit;

	/* The 3-byte item round-trips through the written file. */
	file = gf_isom_open(path, GF_ISOM_OPEN_READ, NULL);
	assert_not_null(file);
	if (!file) goto exit;
	e = gf_isom_extract_meta_item_mem(file, GF_TRUE, 0, data_id, &out, &out_size, &out_alloc, NULL, GF_FALSE);
	assert_equal(e, GF_OK, "%d");
	assert_equal(out_size, 3, "%u");
	if (out && out_size == 3) assert_equal_mem(out, "abc", 3);

exit:
	if (file) gf_isom_delete(file);
	gf_file_delete(path);
	if (out) gf_free(out);
	if (payload) gf_free(payload);
	if (empty) gf_free(empty);
#endif
}
