from ricecooker.utils.downloader import ArchiveDownloader

sushi_url = 'https://activecalculus.org/single2e/frontmatter.html'

archive = ArchiveDownloader("downloads/active_calc_2e_again2")

archive.get_page(sushi_url)

result,two  = archive.export_page_as_zip(sushi_url)
