<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0" 
                xmlns:xsl="http://www.w3.org/1999/XSL/Transform" 
                xmlns:sitemap="http://www.sitemaps.org/schemas/sitemap/0.9"
                xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
  <xsl:output method="html" encoding="UTF-8" indent="yes"/>

  <xsl:template match="/">
    <html>
      <head>
        <title>Sitemap</title>
        <style>
          body { font-family: sans-serif; }
          table { width: 100%; border-collapse: collapse; }
          th, td { padding: 8px; border: 1px solid #ddd; text-align: left; }
          th { background-color: #f2f2f2; }
        </style>
      </head>
      <body>
        <h1>Sitemap</h1>
        <xsl:choose>
          <xsl:when test="/sitemap:sitemapindex">
            <h2>Sitemap Index</h2>
            <table>
              <tr>
                <th>Sitemap URL</th>
                <th>Last Modified</th>
              </tr>
              <xsl:for-each select="sitemap:sitemapindex/sitemap:sitemap">
                <tr>
                  <td>
                    <xsl:variable name="sitemapURL" select="sitemap:loc"/>
                    <a href="{$sitemapURL}"><xsl:value-of select="$sitemapURL"/></a>
                  </td>
                  <td>
                    <xsl:value-of select="sitemap:lastmod"/>
                  </td>
                </tr>
              </xsl:for-each>
            </table>
          </xsl:when>
          <xsl:when test="/sitemap:urlset">
            <h2>URL Set</h2>
            <table>
              <tr>
                <th>URL</th>
                <th>Images</th>
                <th>Last Modified</th>
                <th>Publication Name</th>
                <th>Publication Date</th>
                <th>Title</th>
              </tr>
              <xsl:for-each select="sitemap:urlset/sitemap:url">
                <tr>
                  <td>
                    <xsl:variable name="url" select="sitemap:loc"/>
                    <a href="{$url}"><xsl:value-of select="$url"/></a>
                  </td>
                  <td>
                    1
                  </td>
                  <td>
                    <xsl:value-of select="sitemap:lastmod"/>
                  </td>
                  <td>
                    <xsl:value-of select="news:news/news:publication/news:name"/>
                  </td>
                  <td>
                    <xsl:value-of select="news:news/news:publication_date"/>
                  </td>
                  <td>
                    <xsl:value-of select="news:news/news:title"/>
                  </td>
                </tr>
              </xsl:for-each>
            </table>
          </xsl:when>
          <xsl:otherwise>
            <p>This is not a valid sitemap or sitemap index file.</p>
          </xsl:otherwise>
        </xsl:choose>
      </body>
    </html>
  </xsl:template>

</xsl:stylesheet>