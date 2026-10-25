// tidy-html5 issue #1177: the reproducer from the issue text (written out here, not downloaded).
#include "tidy.h"
#include "tidybuffio.h"

int main(void) {
  const char *html = "<html><body><p>hello</p></body></html>";

  TidyDoc tdoc = tidyCreate();
  TidyBuffer errbuf, output;
  tidyBufInit(&errbuf);
  tidyBufInit(&output);
  tidySetErrorBuffer(tdoc, &errbuf);
  tidyOptSetBool(tdoc, TidyXhtmlOut, yes);

  tidyParseString(tdoc, html);
  tidyCleanAndRepair(tdoc);
  tidyRunDiagnostics(tdoc);
  tidyOptSetBool(tdoc, TidyForceOutput, yes);
  tidySaveBuffer(tdoc, &output);

  tidyBufFree(&output);
  tidyBufFree(&errbuf);
  tidyRelease(tdoc);
  return 0;
}
