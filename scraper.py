import scrapy
from scrapy.crawler import CrawlerProcess
import requests
import os
import pandas as pd
from bs4 import BeautifulSoup
from gradio_client import Client, handle_file

# Your Zyte spider
class MeritListSpider(scrapy.Spider):
    name = 'merit_list'
    start_urls = ['https://ugadmissions.nust.edu.pk/result/meritsearch.aspx']
    
    def __init__(self, roll_number_suffix, start_range, end_range, *args, **kwargs):
        super(MeritListSpider, self).__init__(*args, **kwargs)
        self.roll_number_suffix = roll_number_suffix
        self.start_range = start_range
        self.end_range = end_range
        self.client = Client("Nischay103/captcha_recognition")
        self.temp_folder = 'temp_captchas'
        os.makedirs(self.temp_folder, exist_ok=True)
        self.results = []
    
    def generate_roll_numbers(self):
        return [f"{i:06d}{self.roll_number_suffix}" for i in range(self.start_range, self.end_range + 1)]
    
    def parse(self, response):
        roll_numbers = self.generate_roll_numbers()
        
        for roll_number in roll_numbers:
            captcha_url = self.fetch_captcha_image(response)
            if captcha_url:
                yield scrapy.Request(captcha_url, callback=self.solve_captcha, meta={'roll_number': roll_number})
    
    def fetch_captcha_image(self, response):
        # Use BeautifulSoup to parse the CAPTCHA image source
        soup = BeautifulSoup(response.text, 'html.parser')
        captcha_image_tag = soup.find("img", id="ctl00_ctl00_ctl00_Body_Body_cpResultBody_RadCaptcha1_CaptchaImage")
        
        if captcha_image_tag:
            src = captcha_image_tag["src"]
            return f"https://ugadmissions.nust.edu.pk{src.replace('..', '')}" if src.startswith("..") else src
        return None
    
    def solve_captcha(self, response):
        roll_number = response.meta['roll_number']
        
        captcha_image_path = os.path.join(self.temp_folder, f"captcha_{roll_number}.png")
        with open(captcha_image_path, 'wb') as f:
            f.write(response.body)
        
        result = self.client.predict(input=handle_file(captcha_image_path), api_name="/predict")
        predicted_text = result.upper()
        
        formdata = {
            "Body_Body_cpResultBody_txtRollNo": roll_number,
            "ctl00_ctl00_ctl00_Body_Body_cpResultBody_RadCaptcha1_CaptchaTextBox": predicted_text,
        }
        
        yield scrapy.FormRequest(
            url="https://ugadmissions.nust.edu.pk/result/meritsearch.aspx",
            formdata=formdata,
            callback=self.parse_merit_result,
            meta={'roll_number': roll_number}
        )
    
    def parse_merit_result(self, response):
        roll_number = response.meta['roll_number']
        if "meritresult.aspx" in response.url:
            # Extract information from the page
            reg_no = response.xpath("//span[@id='Body_Body_lblRollNo']/text()").get().strip()
            name = response.xpath("//span[@id='Body_Body_lblName']/text()").get().strip()
            father_name = response.xpath("//span[@id='Body_Body_lblFatherName']/text()").get().strip()

            # Process merit table
            rows = response.xpath("//div[@id='Body_Body_divBBAMerit']//table/tbody/tr")
            for row in rows[1:]:
                selection_list_no = row.xpath("./td[1]/text()").get().strip()
                programme = row.xpath("./td[2]/text()").get().strip()
                merit_position = row.xpath("./td[3]/text()").get().strip()
                status = row.xpath("./td[4]/text()").get().strip()
                
                self.results.append([roll_number, name, father_name, selection_list_no, programme, merit_position, status])
        else:
            self.results.append([roll_number, 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A'])
    
    def closed(self, reason):
        df = pd.DataFrame(self.results, columns=['Roll No', 'Name', 'Father Name', 'Selection List No', 'Programme', 'Merit Position', 'Status'])
        df.to_csv('merit_list.csv', index=False)
        print(f"Scraping finished. Results saved to merit_list.csv")

# Running the spider
if __name__ == '__main__':
    process = CrawlerProcess()
    process.crawl(MeritListSpider, roll_number_suffix="244", start_range=100000, end_range=100079)
    process.start()
